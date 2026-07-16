# AGENTS.md — CRM-MailServer (onlyoffice-mail enhancement)

**Project**: Fork of ONLYOFFICE/Docker-MailServer → https://github.com/kachapman/CRM-MailServer
**Primary goal**: Add a robust parallel API (FastAPI on port 8090) providing full mail functionality (list, read/unread, bodies, attachments, move/mark, account filtering) so external apps (e.g. Vanguard CRM dashboard) can use it. Support mbsync-based full local mirroring of external IMAP accounts (managed in CS mail module) as shared receive-only "CRM base" / universal inboxes. **Maintain 100% backward compatibility** with ONLYOFFICE Community Server (CS).

**Key links**:
- Living plan: `PLAN.md` (read this on every session)
- API design: `docs/robust-mail-api-design.md`
- Using the API: `docs/using-robust-api.md`
- Dashboard reference shapes: `dashboard_reference_docs/dashboard_mail_modal_issues.md`
- CRM base accounts: `crm@vanguardadj.online`, `requests@sherwoodestimates.com` (receive-only, full-folder mirror)

**Status (as of latest push)**: 
- PLAN.md updated with detailed CS compatibility analysis (section 3b), current progress, and open questions.
- Basic skeleton exists: `crm_mail_api/`, Dockerfile updates, guarded start in `iRedMail/run_mailserver.sh`.
- SSH push to fork works (see below).

## Critical Invariants (NEVER BREAK THESE)

- Legacy provisioning API on **exactly port 8081** (Ruby posty_API / mailserver_api-2.0.1 via Passenger/httpd) must continue to work unchanged for CS.
- Token generation (`INSERT IGNORE api_keys id=1` using md5 in `run_mailserver.sh`) and lookup must remain identical.
- No breaking changes to core vmail schema (`samples/iredmail.mysql`), Dovecot config generation (`functions/dovecot.sh`, samples/dovecot/*), Postfix maps, or maildir layout (`conf/core` hash_maildir + MAILDIR_STYLE=hashed).
- All `mailbox` rows (including for mirrored CRM bases) must set: correct `storagenode`/`maildir`, full `enable*` flags (at minimum `enableimap=1`, `enabledeliver=1`, `enabledoveadm=1`, `active=1`; `enablesmtp=0` for receive-only), `domain` row present.
- CS direct DB writes (via MAIL_SERVER_DB_*) and its own `mail_*` tables for externals must not be disturbed.
- Startup order: services (incl. dovecot) first, then background CRM API.
- Use `doveadm` as primary for local mail ops (respects indexes, ACLs, namespaces).
- Mirroring (when implemented): mbsync for full local copy of all folders; background + explicit force; one-time initial full copy. Errors must be surfaced.
- **Always** test legacy CS provisioning + mail flows after any Dockerfile, run_*.sh, or script change.
- Features for the new API/mirroring are additive and should be behind env flags where possible (`ENABLE_CRM_MAIL_API`, future `ENABLE_MBSYNC_MIRROR`).

## Architecture Notes (reuse these)

- Parallel service only: new code lives in `crm_mail_api/` (FastAPI + uvicorn). Legacy 8081 untouched.
- Auth: reuse global token from `api_keys` table (header `AUTH_TOKEN` or `?auth_token=`). Same as CS uses.
- Mail access: `crm_mail_api/doveadm.py` wrapper around `/usr/bin/doveadm -u <username> ...`
- CRM bases: marked in `crm_mail_accounts` table (or via `mailbox.settings`). Fixed receive-only accounts created with helper `tools/create_crm_mail_account.py`.
- Folder IDs: emulate CS magic numbers where possible (1=INBOX, 4=Trash, ...). See `crm_mail_api/main.py` FOLDER_MAP.
- Response shapes: target compatibility with what dashboard consumes from CS `/api/2.0/mail/*` (conversations, mark via ids[], accountId filter). See dashboard_reference_docs/.
- External mirroring: full local maildir copy via mbsync (not live proxy). Takeover means dashboard switches specific accountIds to call 8090 instead of CS.
- Shared access: global token + direct doveadm on the CRM base mailbox (multi-user via app permissions). Dovecot already has `namespace { type=shared; prefix=Shared/%%u/; ... }` but current API bypasses it.

## Useful Commands & Testing

**Build the image** (from project root):
```bash
docker build -t onlyoffice-mail-crm .
```

**Run (example, see README.md for full vars/volumes/network)**:
```bash
docker run --init --net onlyoffice --privileged -d --name onlyoffice-mail-crm \
  -p 8090:8090 -p 8081:8081 -p 143:143 ... \
  -e MYSQL_SERVER=... \
  -e ENABLE_CRM_MAIL_API=YES \
  -e CRM_MAIL_API_PORT=8090 \
  onlyoffice-mail-crm
```

**Inside container (for debugging)**:
- `doveadm -u user@dom mailbox list`
- `python3 -m uvicorn crm_mail_api.main:app --host 0.0.0.0 --port 8090`
- Check logs: the run_mailserver.sh starts the uvicorn in background if enabled.

**Test legacy CS compat**:
- After changes, verify 8081 still responds to CS provisioning calls.
- Normal mailboxes still work via IMAP and CS mail module.
- Token from api_keys is usable by both 8081 and 8090.

**Local Python dev for the API** (if Python env available):
```bash
cd crm_mail_api
python -m uvicorn main:app --reload --port 8090
```

**Git**:
- This repo uses the kachapman fork for our work.
- Current remotes: `fork` (SSH to kachapman), `origin` (upstream ONLYOFFICE).
- Always commit plan/docs updates promptly.

**mbsync / mirroring (future)**:
- Will be optional.
- Per-account config + background process + force endpoint.
- Must not race with CS polling (takeover = disable in CS mail module for the accounts).

## Session Rules for Agents

- **Always start by**:
  1. Reading `PLAN.md` (especially status, section 3b compatibility risks, open questions, current progress).
  2. Running `git status` and `git log --oneline -5` to see exact current state.
  3. Using search/read tools (grep, read, glob) before editing — do not assume prior file contents.
- Preserve exact file paths, commands, error strings, and identifiers in plans/notes.
- Make changes **additive** for new features. Use env flags for optional parts (mbsync, etc.).
- After edits: run relevant lint/type/build steps if available; at minimum verify no breakage to startup/legacy paths.
- For compatibility work: always document file:line references (e.g. `iRedMail/run_mailserver.sh:66`).
- When weighing tradeoffs (e.g. direct IMAP sharing vs API-only, credential handling for mbsync), ask the user with clear options.
- Update `PLAN.md` (and this AGENTS.md) with decisions and completed work.
- This project is read/write in build mode. Plan mode is for pure analysis only.

## Current Open Questions (see PLAN.md for full list + context)

1. Sharing model: Is global-token API (doveadm -u) enough for multi-user CRM bases, or do we need direct IMAP via the existing Shared/%%u/ namespace?
2. mbsync creds: Manual config, one-time import, or read from CS DB?
3. Takeover: Must CS stop polling the two externals, or support parallel (with desync risk)?
4. Error display: What exact status fields for dashboard + mail module (last_error, timestamp, per-folder, etc.)?

## Next / Focus Areas
- Complete doveadm implementation for mark/move/bodies/attachments + folder emulation.
- mbsync integration (background + force + status).
- Proper CRM base account creation with exact hash/flags.
- End-to-end compat verification (CS + new API).
- Answers to open questions above will unblock final mirroring details.

This file provides persistent context so future sessions (human or agent) can resume quickly. It is complementary to `PLAN.md`.

Update this file when architecture, key commands, or invariants change.
