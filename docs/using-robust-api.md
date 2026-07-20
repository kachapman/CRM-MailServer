# Using the Robust Mail API (CRM Mail)

The parallel service on port 8090 provides full mail functionality for external applications and CRM dashboards.

## Auth
Use the same global token as the legacy API:

```
AUTH_TOKEN: <the token from api_keys table or generated at startup>
```

Or `?auth_token=...`

The token is the same one used by ONLYOFFICE Community Server.

## Key Endpoints

- `GET /api/v1/mail/accounts` — list all mailboxes. `type: "crm"` for universal/CRM record inboxes.
- `GET /api/v1/mail/folders?accountId=user@dom` — folders for a specific account.
- `GET /api/v1/mail/conversations.json?accountId=...&folder=1&unread=true` — main list (supports account filtering for CRM vs other inboxes). Returns `read` status.
- `PUT /api/v1/mail/conversations/mark.json?ids[]=123&status=read&accountId=...`
- `PUT /api/v1/mail/conversations/move.json?ids[]=123&folder=4&accountId=...`
- `GET /api/v1/mail/conversation/{id}.json?accountId=...` — detail with body.

## CRM Mail / Universal Receive-Only Accounts

Use the helper:

```bash
python /usr/src/iRedMail/tools/create_crm_mail_account.py crm@yourdomain.com "CRM Record Inbox"
```

Then configure delivery (BCC, alias, sieve) as printed by the script.

The API will return those accounts with `"type": "crm"` and allow filtering by `accountId`.

## Example curl (after getting token)

```bash
TOKEN=...  # from api_keys or env

curl -H "AUTH_TOKEN: $TOKEN" \
  "http://mailserver:8090/api/v1/mail/accounts"

curl -H "AUTH_TOKEN: $TOKEN" \
  "http://mailserver:8090/api/v1/mail/conversations.json?accountId=crm@yourdomain.com&unread=true"
```

## Read/Unread
The `read` boolean comes directly from the `\Seen` flag via doveadm.

Marking updates the flag in Dovecot.

## Compatibility
- Legacy API on 8081 unchanged.
- Community Server continues to work.
- This API is additive for external / custom CRM use.

See PLAN.md for full roadmap.
