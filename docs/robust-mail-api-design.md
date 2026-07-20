# Robust Mail API Design (Parallel Service)

**Status**: Draft (see PLAN.md for overall context)

**Port (proposed)**: 8090  
**Base path**: `/api/v1/mail` (or `/api/mail` — TBD after first prototype)  
**Auth**: Same global token as legacy API (`AUTH_TOKEN` header or `auth_token` query param). Look up in `api_keys` table (existing logic).

## Design Principles
- Additive only. Legacy 8081 Ruby service untouched.
- Full scope: accounts, folders, conversations/messages list+detail, bodies, attachments (download), mark read/unread, move/delete, search/filter.
- Primary filter requirement: every message/conversation response **must** expose the receiving email account/mailbox so external apps can filter ("CRM Mail" vs other inboxes).
- Response shapes should be as close as practical to what the dashboard already consumes from Community Server `/api/2.0/mail/*` (see `dashboard_reference_docs/dashboard_mail_modal_issues.md`).
- Use doveadm as the primary backend for queries and mutations (reliable, ACL/namespace aware).
- Receive-only "CRM Mail" / universal accounts are user-provisioned (aliases, sieve, BCC). Server only provides the marker + visibility in data.

## Proposed Endpoints (v1)

### Accounts & Structure
```
GET /api/v1/mail/accounts
  -> [{ id, email, name, type: "crm" | "normal", enabled: bool, quota?, folders: [...]?, unread? }]

GET /api/v1/mail/folders?accountId=xxx
  -> [{ id: 1, name: "INBOX", special_use: "\\Inbox", unreadCount, totalCount }, ...]
  (Use OnlyOffice-style folder ids where possible: 1=Inbox, 4=Trash, etc. for dashboard compat)
```

### Conversations / Messages (with account filtering)
```
GET /api/v1/mail/conversations.json
  Query params (match dashboard usage):
    folder=1
    accountId=...          # CRITICAL for CRM Mail filtering
    page=0
    page_size=20
    sort=date
    sortorder=descending
    unread=true|false
    from=...
    subject=...
    hasAttachment=true
    since=... before=...

  Response (shape inspired by CS):
  {
    "count": 123,
    "conversations": [
      {
        "id": 456,                    # conversation id (or stable thread key)
        "subject": "...",
        "from": { "name": "...", "email": "..." },
        "date": "2026-...",
        "read": false,
        "account": { "id": "...", "email": "crm@...", "type": "crm" },
        "folderId": 1,
        "hasAttachments": true,
        "messageCount": 3,
        ...
      }
    ]
  }
```

```
GET /api/v1/mail/conversation/{id}.json?loadAll=false
  -> { id, subject, from, to, cc, bcc, date, read, account, messages: [ {id, bodyHtml?, bodyText?, attachments: [...] } ] , ... }
```

```
GET /api/v1/mail/messages/{id}   (or per-part)
GET /api/v1/mail/messages/{id}/raw
GET /api/v1/mail/messages/{id}/attachments/{attId}   (binary stream, with proper Content-Disposition)
```

### Mutations (full scope)
```
PUT /api/v1/mail/conversations/mark.json
  Body (form or json): ids[]=123&ids[]=456&status=read   (or unread)

PUT /api/v1/mail/conversations/move.json
  ids[]=...&folder=4   # 4 = trash to match native

DELETE /api/v1/mail/conversations   (or move to trash + expunge variant)
```

### Search / Advanced Filter
- Reuse the list endpoint with additional params.
- Future: full-text via doveadm search `TEXT "foo"`.

### CRM-Specific (lightweight)
```
POST /api/v1/mail/crm/link
  { "messageIds": [...], "crmEntityType": "opportunity", "crmEntityId": "..." }

GET /api/v1/mail/crm/links?messageId=...
```

### Health / Meta
```
GET /api/v1/mail/version
GET /health
```

## Response Compatibility Notes
- Use the conversation list + detail flow the dashboard switched to in v1.7.0.
- Include `account` (or `mailbox` + `targetEmail`) at every level so the external app can:
  - Filter the modal by account.
  - Show "CRM" vs "REQ" badges.
  - Know the record inbox source for linking/scanner.
- Folder numbers: try to emit the same magic numbers OnlyOffice uses (Inbox=1, Trash=4, etc.).
- For bodies: provide `htmlBody`, `textBody`, and attachment array with `name`, `size`, `contentType`, `downloadUrl`.
- Auth errors: 401 with similar message to legacy.

## Backend Implementation Sketch
- Python (FastAPI) service.
- On startup: connect to MySQL (reuse `MAIL_SERVER_DB_*` or `VMAIL_*` envs), discover token table.
- Auth dependency: look up active token (same as current `api_keys`).
- Mail ops module:
  - `list_accounts()`
  - `list_folders(account)`
  - `search_conversations(filters)` → calls `doveadm -u <user> search ...` then enriches with account info.
  - `fetch_message(uid, parts=["flags","hdr","body"])` 
  - `set_flags(uids, add=["\\Seen"], remove=[])`
  - `move(uids, dest_folder)`
- For CRM accounts: new small table `crm_mail_accounts` (or reuse `mailbox.settings` JSON) with `username`, `type='crm'`, `description`.
- When building responses, join or lookup the receiving mailbox for every hit (doveadm can give the user; map back via DB).

## Doveadm Command Examples (to be used by the service)
```bash
# List folders for user
doveadm -u user@dom mailbox list

# Search unseen in Inbox
doveadm -u user@dom search -r INBOX UNSEEN

# Fetch uid + flags + key headers for recent
doveadm -u user@dom fetch 'uid flags hdr.subject hdr.from hdr.date hdr.message-id' mailbox INBOX 1:*

# Mark seen
doveadm -u user@dom flags add '\Seen' mailbox INBOX uid 42

# Move to Trash
doveadm -u user@dom move Trash mailbox INBOX uid 42

# For shared/public (universal)
doveadm -u publicuser mailbox list -u '*'
# or use namespace prefix + ACL
```

Master user auth (if needed for cross-mailbox):
- Configure a master user in the passwd-file.
- Then `doveadm -u target@dom -o auth_master_user_separator=* ...` or similar.

## Account / Mailbox Awareness (for filtering)
Every listed item must carry:
```json
"account": {
  "id": "crm@vanguardadj.online",
  "email": "crm@vanguardadj.online",
  "type": "crm",           # or "normal"
  "displayName": "CRM Record Inbox"
}
```

This satisfies "when the emails are pulled, the external application can see what emails came from what email account" and enables account selector + CRM vs REQ differentiation.

## Attachments & Bodies (Full Scope)
- Parse MIME once per fetch (cache lightly if helpful).
- Provide both:
  - Inline in detail response (text + html if small).
  - Dedicated download URLs for attachments (auth checked via the same token).
- Support large attachments via streaming (FastAPI `StreamingResponse`).

## CRM Mail Provisioning Helpers
- `tools/create_crm_mail_account.py` (or endpoint) that:
  1. Creates mailbox (reuse existing logic or call dovecot/postfix tools).
  2. Marks it in the CRM accounts table.
  3. Prints suggested alias / sieve snippets for user to apply.
- Docs emphasize: no auto-BCC in the server; configure at send time or via sieve/aliases.

## Open Decisions
- Exact URL prefix and whether we emulate `/api/2.0/mail` paths for easier dashboard swap.
- Stable conversation IDs (may need a thin `mail_conversations` or `mail_threads` table).
- How much conversation threading logic to implement vs. returning messages + headers for client-side grouping.
- Attachment content disposition / filename sanitization.
- Whether to support sending (append to Sent + SMTP) in v1.

## See Also
- `PLAN.md` (main plan)
- `dashboard_reference_docs/dashboard_mail_modal_issues.md`
- Legacy API source (tarball)
- Dovecot namespaces + ACL samples in `iRedMail/samples/dovecot/`
