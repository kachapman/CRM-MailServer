# CRM-MailServer Enhancement Plan

**Project**: Fork of ONLYOFFICE/Docker-MailServer → https://github.com/kachapman/CRM-MailServer  
**Goal**: Add a robust, full-featured mail API (parallel service) so external applications (e.g. custom Vanguard CRM dashboard email modal) can achieve near-identical functionality to native ONLYOFFICE Community Server mail usage, without breaking existing Community Server (CS) integration.

**Date started**: 2026-07-14  
**Status**: Plan + extensive read-only compatibility analysis complete. Skeleton code + Docker integration exists (parallel API on 8090). Now in build mode. Updated with detailed CS risks, progress, and open questions. (2026-07-15)

## 1. Background & Context from User

- Current ONLYOFFICE Mail Server (iRedMail-based) provides:
  - Standard MTA/MDA (Postfix + Dovecot).
  - Legacy provisioning API (Ruby posty_API / mailserver_api-2.0.1 on port 8081) used by CS for domain/mailbox management.
  - Everything is strictly per-user siloed.
  - No native REST access to messages, read/unread flags, bodies, attachments, or cross-account views.

- User's dashboard (kanban CRM) currently:
  - Proxies calls to Community Server's `/api/2.0/mail/*` endpoints (conversations, mark, move, link, accounts, folders, tags, etc.).
  - Uses **conversation-level** operations for mark read/unread, delete, CRM linking.
  - Has "CRM Mail" / record inbox use case:
    - Special receive-only BCC mailboxes (e.g. `crm@vanguardadj.online`).
    - Correspondence BCC'd here is the canonical record for deals in CRM.
    - Scanner classifies, links emails to opportunities, applies policies (record inbox = link-only, no tasks).
    - Needs to know **which email account** (receiving mailbox) an email arrived for, to filter and differentiate inboxes (CRM vs action/REQ inboxes).
  - Email modal needs: list (conversations), detail (with body/attachments), mark read/unread, delete/move, link to CRM, tags, account selector/filter, unread badges.
  - Reference docs placed in `dashboard_reference_docs/` (dashboard_mail_modal_issues.md is especially important — details exact endpoints and why conversations vs messages).

- Requirements (numbered per user answers):
  1. Scope = **full** (list, bodies, attachments, flags, move/delete, search, etc.).
  2. Universal inbox = "CRM Mail" / record inbox: receive-only accounts that receive via BCC (or user-configured aliases/sieve). No auto-population of mail into it. Users configure delivery.
  3. Filtering: external app must filter/pull by email account (receiving mailbox must be visible in responses).
  4. Auth: reuse the existing global API token (same as current `api_keys` + AUTH_TOKEN).
  5. **Parallel service** for the new robust API (do not modify the legacy 8081 Ruby service).
  6. Modernize base image where possible, **provided** CS compatibility is preserved.
  7. No auto delivery logic for universal/CRM Mail.
  8. Return data shapes that existing dashboard code expects / can easily adapt to (bodies + attachments already consumed via the old mail module API).
  9. Reference the official ONLYOFFICE Workspace API docs (the `/api/2.0/...` layer that sits on top of mail).

- CS must continue to work unchanged for the Community Server CRM module they use.

## 2. High-Level Architecture

```
[ ONLYOFFICE Community Server ]  <-- uses legacy API + direct DB + IMAP
         |
         v  (existing, unchanged)
[ MailServer Docker ]
  - Legacy provisioning API (Ruby/Grape on :8081)  <-- KEEP FOR CS COMPAT
  - Dovecot (IMAP 143/993, managesieve 4190)
  - Postfix, etc.
  - NEW: Robust Mail API service (parallel, e.g. Python FastAPI on :8090 or :8082)
         |
         +-- Auth via global token (reused from api_keys)
         +-- Direct access to vmail DB + maildirs + doveadm
         +-- Full message/conversation ops, flags, bodies, attachments
         +-- Account/mailbox awareness for filtering
         +-- Special support for "CRM Mail" / universal receive-only accounts
```

- **Parallel service name suggestion**: `crm-mail-api` or `robust-mail-api`.
- New port: recommend **8090** (avoid collision with common ports; expose in Dockerfile).
- The new service will be **additive** — existing run scripts, httpd, passenger, legacy API untouched.
- External apps (dashboard) can call the new service directly (or via a thin proxy) for mail data.

## 3. Compatibility Requirements (Non-Negotiable)

- Legacy Ruby API on 8081 + all its responses, token generation (`run_mailserver.sh` md5 insert for id=1), and behavior **must not change**.
- CS env vars (`MAIL_SERVER_API_HOST`, `MAIL_SERVER_DB_*`, etc.) and the way CS writes to the vmail DB continue to work.
- IMAP/SMTP/managesieve surface unchanged.
- No schema changes that break existing CS queries or iRedMail tools.
- Docker networking, volumes, startup (`install_mail.sh`, `run_mailserver.sh`, `external.sh` hook) remain working.
- When modernizing base, the resulting container must still answer the same provisioning calls that CS makes.

## 3b. Community Server Compatibility Analysis (Detailed Review - July 2026)

Extensive read-only inspection performed (grep, read, glob, delegated explore on key scripts, samples, confs, DB schema, startup, dovecot, legacy API tarball, creation tools, current crm_mail_api).

**Core CS integration points (must remain identical):**
- Legacy Ruby API on exactly **8081** (Passenger + mailserver_api-2.0.1). See `iRedMail/functions/server_api.sh:54`, `conf/server_api`, pkgs tarball (`app/api/v1.rb`, models/mailbox.rb using username PK).
- Token: `INSERT IGNORE INTO api_keys (id=1, ...)` using md5(date) in `iRedMail/run_mailserver.sh:60-66`. Legacy rake also touches it. CS reads it for its mail_server_server config + AUTH_TOKEN.
- Direct DB writes by CS (via MAIL_SERVER_DB_* creds) to vmail tables + its private `mail_*` tables (external accounts, polling state, UIDs, folders in onlyoffice DB).
- Dovecot config generated from samples (`dovecot22.conf`, `dovecot-sql.conf`): user/password queries rely on `enable%Ls%Lc=1 AND active=1`, `mail_location = maildir:%Lh/Maildir/:INDEX=...`, special-use folders, shared namespace `prefix=Shared/%%u/`, ACL, master-user `*` separator. Rewrites in `functions/dovecot.sh:147`.
- Mailbox creation paths must match exactly: `storagebasedirectory`, `storagenode`, hashed `maildir` (see `conf/core:265 hash_maildir`, `conf/global:43 MAILDIR_STYLE=hashed`), full `enable*` flags (enablesmtp=0 ok for receive-only but enableimap=1, enabledeliver=1, enabledoveadm=1, etc. required), `active=1`, `quota`, `settings TEXT`, `local_part`. Postfix maps e.g. `samples/postfix/mysql/virtual_mailbox_maps.cf:6` require `enabledeliver=1`.
- Startup order in `run_mailserver.sh:74+`: mysql wait → token → dovecot → ... httpd (8081) → (background crm api). No current wait for dovecot before doveadm.
- Schema: `samples/iredmail.mysql:130` (mailbox 50+ cols, PK username), `share_folder`, `used_quota` + trigger (dovecot managed), `api_keys` (samples/server_api/mysql.cf).
- Existing sync: only one-way `imapsync_batch.py` (deprecated).

**Major Risks Identified + Mitigations (to be respected in all changes):**
- **Dual provisioning / username+maildir collisions**: `tools/create_crm_mail_account.py`, `create_mailboxes.py:155`, `functions/mysql.sh:191`, legacy API, and CS direct inserts can diverge on maildir hash, missing domain row, incomplete enable* flags → postfix reject or dovecot fail. *Mitigation*: Use exact `hash_maildir` from conf/core; ensure domain row; full column INSERT matching schema; central helper; prefer 8081 calls when possible. Add validation.
- **Token & 8081 fidelity**: Changes to run script or Dockerfile build can alter token or delay httpd. *Mitigation*: Never touch the INSERT logic or 8081 config. crm api strictly reads same token.
- **External account dual-polling & state divergence**: CS polls externals (crm@, requests@) via its mail_* tables + stored IMAP creds. mbsync + new API mutations on local mirror will race on \Seen, deletes, UIDs. *Mitigation*: Takeover requires disabling the account in CS mail module for those addresses. mbsync initially receive-only / one-way where possible; use state dirs, careful expunge; expose sync status/errors in robust API for dashboard + mail module. Document "single writer" assumption broken by mirroring.
- **Dovecot maildir / shared / ACL / query breakage**: doveadm.py + mbsync concurrent access corrupts INDEX/flags. Shared namespace exists but current API ignores it. enable*=0 blocks access. *Mitigation*: Set all required enable* even for receive-only CRM bases. Run mbsync post-dovecot as vmail user; use `--no-expunge` or doveadm sync for bidirectional; update doveadm wrapper for namespaces/special-use. Add dovecot readiness wait before crm api start (`run_mailserver.sh`).
- **Schema / additive-only**: New tables ok (`crm_mail_accounts` with IF NOT EXISTS), but no ALTERs to mailbox etc. CS assumes exact tables + queries.
- **Startup races**: Background uvicorn (already present) + future mbsync may call doveadm before ready. *Mitigation*: Add explicit waits (like mysql wait).
- **Folder IDs & shapes for takeover**: Dashboard expects specific folder nums (1=INBOX, 4=Trash), conversation objects. *Mitigation*: Maintain FOLDER_MAP + shapes in crm_mail_api (see current main.py:174 and dashboard_reference_docs/).
- **mbsync on ancient base**: CentOS 6.7 + isync install risky; no current support. *Mitigation*: Make optional (`ENABLE_MBSYNC_MIRROR=YES`); install only when enabled; test thoroughly.
- **Long-term modernization**: Every additive change (Python, mbsync) makes base upgrade harder. Validate CS end-to-end after any change.
- **Other**: Quota/lastlogin/settings population; used_quota triggers; no direct writes to dovecot tables.

**Safeguards for all future work**:
- Everything mirroring/8090/CRM behind env flags (safe defaults = no change to CS).
- Validation + exact hash + full flags on any mailbox creation for mirrors.
- End-to-end test gates: CS provisioning via 8081 still works + normal IMAP + new API for CRM bases.
- Keep legacy 8081, run sequence order, and generated configs pristine.

See full analysis in conversation history / agent output for line-specific snippets.

## 4. Universal / CRM Mail (Receive-Only Record Inbox)

- Concept: one or more special mailboxes (e.g. `crm@domain`) designated as "CRM Mail" or "universal".
- These are **receive-only** for the purpose of recording BCC'd correspondence.
- No automatic population or rewriting of mail by the server. Users/admins configure delivery:
  - Postfix aliases / virtual aliases that point to the CRM mailbox.
  - Sieve rules (global or per-sender) that `fileinto` or `redirect` copies.
  - BCC on the sending side (most common for their use: contractor sending addresses BCC the CRM address).
- The API must:
  - Allow listing/designating CRM Mail accounts (new table or marker in `mailbox.settings` or dedicated `crm_mail_accounts`).
  - When returning messages/conversations, include the receiving account/mailbox (e.g. `account: { id, email, type: "crm" }` or `mailbox` / `folder` info + original `to`/`bcc`).
  - Support filtering by account (so dashboard can do "CRM" vs "REQ" views).
- Later: perhaps a "record" tag or metadata flag on ingestion, but keep server side minimal.

## 5. New Parallel API Surface (Target)

Goal: make it possible for the dashboard email modal to switch (or dual-call) to this service and get full functionality.

Model responses after the shapes the dashboard already consumes from `/api/2.0/mail/*` (see `dashboard_reference_docs/dashboard_mail_modal_issues.md`).

Core endpoints (initial v1, under e.g. `/api/v1/mail/...` or `/api/crm-mail/...` — decide in impl):

**Accounts & Structure**
- `GET /api/v1/mail/accounts` — list mailboxes/accounts (include type: crm | normal, enabled folders, unread counts if easy)
- `GET /api/v1/mail/folders?accountId=...` — folders for an account (Inbox=1, Sent, Trash=4, etc. to match native folder ids where possible)
- `GET /api/v1/mail/tags` (if we add lightweight tagging)

**Listing & Filtering (key for "filter based on email account")**
- `GET /api/v1/mail/conversations.json?folder=1&accountId=...&page=...&page_size=...&sort=date&sortorder=descending&unread=...`
  - Must return objects with at least: `id` (conversation id or message id), `subject`, `from`, `date`, `read`/`isRead`, `account` or `mailbox`, `folderId`
  - Support `?unread=true`, account filter, date range, from, hasAttachment, etc.
- `GET /api/v1/mail/conversation/{id}.json?loadAll=false`
- `GET /api/v1/mail/messages` (fallback message-level if needed)

**Read/Unread, Mutations (full scope)**
- `PUT /api/v1/mail/conversations/mark.json` (or equivalent) — `ids[]` + `status=read|unread` (form or JSON)
- `PUT /api/v1/mail/conversations/move.json` — `ids[]` + `folder=4` (trash) etc.
- Delete / permanent delete variants.

**Content (bodies + attachments)**
- Detail endpoints must return (or have sibling endpoints for):
  - HTML body, text body
  - Attachments list: `{id, name, size, contentType, downloadUrl}`
  - `GET /api/v1/mail/messages/{id}/attachments/{attId}` (stream binary)
  - Raw message option for advanced use.

**Search / Filter**
- Full-text capable where doveadm supports.
- Filter by receiving account (primary new requirement).

**CRM Linking (optional but useful)**
- Basic metadata tagging: `POST /api/v1/mail/crm/link` (store `message/conversation id` → `crm_entity_type + id` in a small local table).
- This lets external apps record links without always going through CS history events.
- Or simply return enough data that the dashboard's existing link flow can continue to work.

**Auth**
- Same global token mechanism:
  - Header: `AUTH_TOKEN: <token>`
  - Or `?auth_token=...`
- Token comes from the existing `api_keys` table (id=1 inserted at startup). No new auth system.

**Other**
- Unread counts / badges helpers.
- Support for the two-inbox model (CRM record vs action) via account filtering + possible `type` or `tag`.

Response shapes should be close enough that minimal changes are needed in `public/app.js` (e.g. `loadMailMessagesForModal`, mark handlers, expand to conversation detail).

## 6. Implementation Technology for Parallel Service

**Recommended**: Python 3.11+ + FastAPI + uvicorn (or gunicorn).
- Reasons: modern, fast to develop, excellent OpenAPI/Swagger (mirrors the "robust API" goal), easy MIME handling, subprocess for doveadm, good Docker story.
- Alternatives considered: Go (faster runtime, but more boilerplate), Node (if team JS-heavy).

**Mail access strategy (in order of preference)**:
1. Primary: `doveadm` CLI (search, fetch flags/headers/body parts, set flags, move). Reliable, respects namespaces, ACLs, indexes.
2. Fallback/supplement: Python `imaplib` / `imapclient` using a Dovecot master user (for full fidelity).
3. Direct maildir + index parsing only as last resort (brittle for flags).

**MIME / attachments**: stdlib `email` + `get_payload`, `walk()`, with safe filename handling. Stream large attachments instead of buffering.

**Threading / conversations**: 
- Start with message-level + `references` / `in-reply-to` headers.
- Provide a "conversations" view that groups by normalized subject or thread-id (simple heuristic first).
- Or store minimal thread info if we want exact parity with CS mail module.
- Dashboard already switched to conversations, so prioritize a list endpoint that returns grouped results or at least stable conversation-like IDs.

**Storage for extras**:
- New table(s) in the vmail DB (or a sidecar sqlite) for:
  - CRM account markers.
  - Link metadata (if implemented).
  - Optional lightweight tags.
- Keep migrations simple and non-breaking.

**Config**:
- Env vars: `ROBUST_MAIL_API_PORT=8090`, `ROBUST_MAIL_API_ENABLED=true`, `CRM_MAIL_ACCOUNT_MARKER=...` or similar.
- Mount for any custom sieve/alias examples.

## 7. Docker & Runtime Integration (No Breakage)

- Dockerfile updates (additive):
  - Install Python + pip + system deps for MIME/doveadm if needed.
  - Copy new service code (e.g. into `/opt/crm-mail-api/`).
  - Add a start script or use supervisor / simple background start in `run_mailserver.sh`.
- Startup order: legacy services first, then new API service (it can wait for dovecot/mysql like the current run script does).
- Expose new port: `EXPOSE 8090`
- Volumes: existing `/var/vmail` gives full maildir access; DB already available.
- Health: simple `/health` or `/version` endpoint.
- `external.sh` hook remains available for user post-start customization.
- Do **not** change the final `tail -f /dev/null` or existing CMD flow in a breaking way.

**Modernization path (phased)**:
- Phase 1 (now): Add parallel service on current CentOS 6.7 base (quick win, zero risk to CS).
- Phase 2: Investigate newer base (Rocky Linux 8/9, Debian 12, or Ubuntu 22.04/24.04) while keeping iRedMail-like provisioning scripts or porting the minimal parts needed for the vmail DB + dovecot config.
- Validate after each base change that:
  - CS still provisions domains/mailboxes via legacy API + DB.
  - IMAP login + flag setting works.
  - New API still works.
- Consider eventually replacing the vendored old Ruby API with a maintained equivalent if we control both sides, but only after proving CS works.

## 8. Delivery to CRM Mail Accounts (User-Configured Only)

- Document clearly in README/PLAN:
  - How to create the receive-only mailbox via existing tools or new API helper.
  - Examples of Postfix alias maps or virtual_alias_maps to deliver or BCC to it.
  - Sieve example: `require ["copy"]; redirect :copy "crm@...";` or `fileinto "CRM";`.
  - Sender-side BCC configuration (their primary pattern).
- Provide a small helper script (e.g. `tools/create_crm_mail_account.py`) that creates the mailbox + marks it as CRM type + prints the alias config snippet.
- No code that automatically adds BCC or rewrites envelopes.

## 9. Data Shapes & "Return What Is Already Existing"

- Study `dashboard_reference_docs/` (especially the issues file) for exact fields expected: conversation id, subject, from, date, read, folder, accountId, etc.
- For bodies/attachments: match what the modal already consumes (HTML/text parts + attachment list with downloadable links).
- Prefer form-urlencoded for mark/move where the dashboard currently sends it (`ids[]` arrays).
- Provide both JSON and form-tolerant parsers in the new service.
- Include `account` / `mailbox` / `targetEmail` prominently in every message/conversation object.

## 10. Phased Implementation Roadmap (High Level)

1. **Plan & Design** (this doc)
   - API surface spec (OpenAPI yaml)
   - Data model for CRM accounts + links
   - Auth reuse details

2. **Skeleton Parallel Service**
   - Add to Dockerfile + deps
   - Basic FastAPI app with token auth (reuse existing key lookup)
   - Health + version
   - Start in run_mailserver.sh (non-blocking)
   - Expose port, test from host

3. **Core Mail Access Layer**
   - Doveadm wrapper module (list folders, search with filters, fetch flags/headers, set \Seen)
   - Account enumeration from `mailbox` table + new CRM marker
   - Basic list conversations/messages with account filter

4. **Full Feature Set (bodies, attachments, mark, move)**
   - MIME extraction
   - Attachment streaming endpoint
   - Mark read/unread via doveadm or IMAP
   - Move to folder / trash
   - Conversation detail

5. **CRM Mail / Universal Support**
   - Marker + listing of CRM accounts
   - Force account info into responses
   - Helper to create marked accounts
   - Docs for user configuration of delivery

6. **Polish & Emulation**
   - Response shapes close to CS mail API
   - Pagination, sorting, unread counts
   - Tags if needed for dashboard
   - Basic CRM link metadata store

7. **Modernization (optional parallel track)**
   - New base image experiments (behind feature flag or separate tag)
   - Validate CS + new API

8. **Testing & Integration**
   - Local dashboard pointing at new API
   - Verify legacy CS flows still work end-to-end
   - Scanner / bot inbox scenarios
   - Account filtering in modal + badge

9. **Docs & Release**
   - Update README with new port, env vars, quickstart for external apps
   - API docs (Swagger + human examples matching dashboard needs)
   - Migration notes

## 11. Open Questions / Decisions (to resolve during impl)

- Exact base path for new API (`/api/v1/mail` vs `/api/2.0/mail` emulation vs `/crm-mail`)?
- Do we want to return conversation IDs that are stable across restarts (may require small thread table)?
- Attachment serving: direct from maildir with auth, or proxy through service with token check?
- Rate limiting / pagination defaults for large inboxes?
- How much of the "link to CRM" do we implement server-side vs let dashboard continue using CS history?
- Folder ID numbering: match OnlyOffice magic numbers (1=Inbox, 4=Trash, ...) for minimal dashboard changes?
- Will the parallel service also handle sending (SMTP submission on behalf of accounts), or is that still via Postfix/IMAP append?

## 12. References

- `dashboard_reference_docs/dashboard_mail_modal_issues.md` (critical — exact endpoints, conversation vs message, mark/delete flows)
- `dashboard_reference_docs/CHANGELOG dashboard-kanban.md` and `AGENTS...` (record inbox policy, two-inbox model, account selector, bot proxy usage)
- Official ONLYOFFICE API doc (linked by user): https://helpcenter.onlyoffice.com/workspace/development/create-api.aspx (custom modules, but shows the /api/2.0 style)
- Existing legacy API: extracted from `iRedMail/pkgs/mailserver_api-2.0.1.tar`
- Current startup: `iRedMail/run_mailserver.sh`, `functions/server_api.sh`, `functions/dovecot.sh`
- Doveadm: primary tool for new service mail ops

## 13. Next Immediate Actions

- [ ] Finalize API spec (OpenAPI) and put in `docs/`
- [ ] Choose port (8090?) and confirm with user
- [ ] Create skeleton `crm_mail_api/` dir + FastAPI hello world + Dockerfile changes
- [ ] Implement token auth against existing `api_keys`
- [ ] Basic doveadm account/folder listing
- [ ] Update this PLAN with decisions as we go
- [ ] Test that legacy 8081 + CS flow still works after any Dockerfile/run changes

---

**This document is the living plan.** Update it with every major decision, architectural change, and completed phase. Keep the dashboard reference docs in sync with any shape changes we introduce.

Push will go to the kachapman fork when ready for commits.

## Current Progress (as of 2026-07-15, build mode active)

### Completed (plan + early build)
- Created/updated `PLAN.md` (this file), `docs/robust-mail-api-design.md`, `docs/using-robust-api.md`.
- Decided: parallel service using **Python + FastAPI + uvicorn** on **port 8090** (legacy 8081 untouched).
- Runnable skeleton implemented:
  - `crm_mail_api/main.py`: token auth (reuses `api_keys` table via global token), /health, accounts, conversations (with accountId filter), mark, move, detail (bodies via doveadm).
  - `crm_mail_api/doveadm.py`: wrapper for list/search/fetch/flags/move.
  - `crm_mail_api/requirements.txt`.
- Docker + runtime integration (additive, non-breaking):
  - `Dockerfile`: Python 3.11 build from source, `COPY crm_mail_api`, `EXPOSE 8090`.
  - `iRedMail/run_mailserver.sh`: INSERT IGNORE api_keys id=1 (md5), guarded background `uvicorn ... &` when `ENABLE_CRM_MAIL_API=YES` (default), respects `CRM_MAIL_API_PORT`.
- Helper: `tools/create_crm_mail_account.py` (creates local mailbox row + `crm_mail_accounts` marker + maildir skeleton; prints alias hints).
- Auth exactly matches legacy (AUTH_TOKEN or ?auth_token= from api_keys).
- Basic account filtering + CRM type support stubbed to enable "filter by inbox" + universal CRM base inboxes.
- No modifications to legacy Ruby 8081, CS provisioning paths, dovecot generation, or core mail flow.
- Full read-only compatibility analysis completed:
  - Inspected: full schema (`iredmail.mysql`), dovecot confs/namespaces/ACLs/queries (`dovecot22.conf`, `dovecot-sql.conf`, `functions/dovecot.sh`), hash logic (`conf/core`, `global`), postfix maps, creation scripts (`create_mailboxes.py`, `mysql.sh`), server_api, startup (`run_mailserver.sh`), legacy tarball, current crm code, dashboard docs.
  - Documented risks (token, dual provisioning, external polling races for mbsync, maildir/UID/flag conflicts, enable* + maildir requirements, startup races, shapes for takeover) + mitigations (see new section 3b).
- External mirroring strategy defined per user: mbsync for full local copy (all folders) of CS-managed externals (crm@vanguardadj.online, requests@sherwoodestimates.com) as fixed receive-only CRM base accounts (type='crm'); background sync + force button/endpoint; one-time initial full copy; errors queryable + displayed in dashboard/mail module; dashboard takes over via robust API for those accounts.
- Current model: full local mirror (not virtual proxy); global token for multi-user access to CRM bases; plain IMAP (no OAuth yet).

### Active / In Progress
- Deepening implementation of doveadm-backed features (mark, move, full bodies/attachments, accurate folder IDs matching CS magic numbers 1/4 etc.).
- Preparing for mbsync integration (optional, flag-gated) + sync status endpoints.
- Ensuring all mailbox creation for mirrors uses exact hash + full flags.

### Blocked / Unknowns
- (none currently; awaiting user answers on open questions below to lock final mirroring + sharing details).

## Updated Open Decisions & Questions (from code review + requirements)

**From initial plan:**
- (same as above: base path, stable conversation IDs, attachment serving, rate limits, CRM link depth, folder numbering, sending support)

**Critical new ones from compatibility + mirroring analysis (answer these to proceed without assumptions):**
1. **Sharing model for universal CRM base accounts**: Dovecot already defines `namespace { type = shared; prefix = Shared/%%u/; ... }` (dovecot22.conf:344). The robust API currently uses direct `doveadm -u <crm-base>` (bypassing shared). Is global-token access via the 8090 API sufficient for "multiple users monitoring the same CRM base accounts" (e.g. crm@ and requests@), or do you also require direct IMAP login/subscription for other clients (Thunderbird etc.) to paths like `Shared/crm-base@.../INBOX` (would require ACL + public/shared config work)?
2. **mbsync credentials source**: How will the mirror obtain the external IMAP passwords (currently stored in CS's `mail_*` tables for those two accounts)? Manual per-account mbsyncrc? One-time secure import? Read from CS DB using the MAIL_SERVER_DB_* creds?
3. **Takeover vs coexistence for the two accounts**: For crm@vanguardadj.online and requests@sherwoodestimates.com, must the CS mail module's polling of the external IMAP be disabled/removed as part of "take over" (strongly recommended to prevent flag/delete/UID races between CS poller + mbsync), or support both CS views and robust API views in parallel (with documented desync risk until CS side is turned off)?
4. **Sync error display contract**: What fields/details must the robust API expose so both the dashboard and the mail module can display errors (e.g. last_error string + timestamp, last successful sync, per-folder status, accountId)? Dedicated endpoint like `/api/v1/mail/sync-status?accountId=...` ?

**Other decisions logged**:
- mbsync over existing imapsync_batch.py for ongoing use.
- Full-folder (all subfolders) background + force; one-time initial full copy.
- CRM bases are fixed/receive-only (`enablesmtp=0`), shared via API + app-level perms; no SMTP.
- Robust API takes over calls for these accountIds in dashboard (shapes compatible with CS /api/2.0/mail/* as much as possible).

## Next Steps (build mode)
- Implement/verify real doveadm for mark/move/bodies/attachments + folder ID emulation.
- Add mbsync support (optional) + status/error endpoints per user spec.
- Update/create CRM base accounts with correct flags + maildir hash.
- Full build/test cycle + legacy CS compatibility verification.
- Update dashboard docs if response shapes refined.
- Commit updates (this PLAN) and continue feature work.
- When answers to questions above received, lock mirroring implementation details and proceed.

---

**Living plan.** Update on every decision and completed item. 

Current git remote is upstream (ONLYOFFICE); target push for this fork work is the kachapman/CRM-MailServer repo as noted in history.
