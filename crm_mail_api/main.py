#!/usr/bin/env python3
"""
crm_mail_api.main
Minimal skeleton for the parallel robust mail API service.

This will become the full-featured mail access layer (conversations, messages,
bodies, attachments, mark read/unread, account filtering, CRM Mail support).

Run: uvicorn crm_mail_api.main:app --host 0.0.0.0 --port 8090

Auth: re-uses the global token from the existing api_keys table
      (same as the legacy Ruby provisioning API on 8081).
"""

from fastapi import FastAPI, Depends, Header, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
import os
import mysql.connector
import subprocess
from datetime import datetime
from typing import Optional, List, Dict, Any  # noqa: F401

from . import doveadm

app = FastAPI(title="CRM Mail Robust API", version="0.1.0")


@app.on_event("startup")
def ensure_crm_tables():
    """Ensure helper tables exist (idempotent)."""
    try:
        conn = mysql.connector.connect(
            host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER,
            password=MYSQL_PASS, database=MYSQL_DB
        )
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS crm_mail_accounts (
                username VARCHAR(255) PRIMARY KEY,
                type VARCHAR(32) NOT NULL DEFAULT 'crm',
                description TEXT,
                created DATETIME,
                modified DATETIME
            ) ENGINE=InnoDB
        """)
        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        pass  # non-fatal during startup

# -------------------------------------------------------------------
# Config (env-driven, compatible with existing MailServer conventions)
# -------------------------------------------------------------------
MYSQL_HOST = os.getenv("MAIL_SERVER_DB_HOST", os.getenv("MYSQL_SERVER", "127.0.0.1"))
MYSQL_PORT = int(os.getenv("MAIL_SERVER_DB_PORT", os.getenv("MYSQL_SERVER_PORT", "3306")))
MYSQL_DB = os.getenv("MAIL_SERVER_DB_NAME", "onlyoffice_mailserver")
MYSQL_USER = os.getenv("MAIL_SERVER_DB_USER", "mail_admin")
MYSQL_PASS = os.getenv("MAIL_SERVER_DB_PASS", "Isadmin123")

def get_db():
    conn = mysql.connector.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASS,
        database=MYSQL_DB,
        autocommit=True
    )
    try:
        yield conn
    finally:
        conn.close()

def get_token_from_header_or_query(
    auth_token: Optional[str] = Header(None, alias="AUTH_TOKEN"),
    auth_token_q: Optional[str] = Query(None, alias="auth_token")
) -> str:
    token = auth_token or auth_token_q
    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized. Missing token.")
    return token

def verify_token(token: str = Depends(get_token_from_header_or_query), db=Depends(get_db)):
    """Validate against the same api_keys table used by the legacy API and CS."""
    cursor = db.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT id, access_token, active, expires_at
        FROM api_keys
        WHERE access_token = %s AND active = 1
          AND (expires_at IS NULL OR expires_at > NOW())
        LIMIT 1
        """,
        (token,)
    )
    row = cursor.fetchone()
    cursor.close()
    if not row:
        raise HTTPException(status_code=401, detail="Unauthorized. Invalid or expired token.")
    return row

# -------------------------------------------------------------------
# Endpoints (skeleton)
# -------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "service": "crm-mail-api"}

@app.get("/api/v1/mail/version")
def version():
    return {"version": "0.1.0-crm", "compatible_with": "legacy-8081-token"}

@app.get("/api/v1/mail/accounts")
def _get_crm_accounts(db) -> set:
    """Return set of usernames that are marked as CRM/universal receive-only accounts."""
    try:
        cur = db.cursor()
        cur.execute("SELECT username FROM crm_mail_accounts WHERE type='crm'")
        rows = cur.fetchall()
        cur.close()
        return {r[0] for r in rows}
    except Exception:
        return set()


@app.get("/api/v1/mail/folders")
def list_folders(accountId: Optional[str] = Query(None), token_info=Depends(verify_token)):
    """List folders for an account (supports account filtering for CRM Mail)."""
    if not accountId:
        return {"folders": [{"id": 1, "name": "INBOX"}]}
    try:
        folders = doveadm.list_folders(accountId)
        return {
            "folders": [
                {"id": idx + 1, "name": f.get("name", "INBOX")}
                for idx, f in enumerate(folders)
            ]
        }
    except Exception:
        return {"folders": [{"id": 1, "name": "INBOX"}]}


def list_accounts(token_info=Depends(verify_token), db=Depends(get_db)):
    """
    List mailboxes/accounts.
    Includes 'type': 'crm' for universal/CRM Mail receive-only accounts.
    """
    crm_set = _get_crm_accounts(db)
    cursor = db.cursor(dictionary=True)
    cursor.execute("""
        SELECT username, name, domain, active, created, modified
        FROM mailbox
        WHERE active=1
        ORDER BY username
        LIMIT 200
    """)
    rows = cursor.fetchall()
    cursor.close()

    accounts = []
    for r in rows:
        email = r["username"]
        accounts.append({
            "id": email,
            "email": email,
            "name": r["name"] or email,
            "type": "crm" if email in crm_set else "normal",
            "active": bool(r["active"]),
        })
    return {"accounts": accounts}

FOLDER_MAP = {
    1: "INBOX",
    4: "Trash",
    # Extend as needed (Sent, Drafts, Junk etc.)
}


def _get_folder_name(folder_id: int) -> str:
    return FOLDER_MAP.get(folder_id, "INBOX")


@app.get("/api/v1/mail/conversations.json")
def list_conversations(
    folder: int = Query(1, description="Folder id (1=Inbox etc.)"),
    accountId: Optional[str] = Query(None, description="Filter by receiving email account (key for CRM Mail)"),
    page: int = 0,
    page_size: int = 20,
    unread: Optional[bool] = None,
    token_info=Depends(verify_token),
    db=Depends(get_db),
):
    """
    List messages (treated as conversations for dashboard compatibility).
    Supports filtering by accountId (receiving mailbox) and unread status.
    Returns read/unread via flags.
    """
    folder_name = _get_folder_name(folder)
    target_user = accountId  # for now we use the email as the dovecot user

    if not target_user:
        # If no accountId, we can list from first active or return empty
        # For safety in CRM use, require account filter or return all (expensive)
        return {"count": 0, "conversations": [], "filters_applied": {"folder": folder, "accountId": None, "unread": unread}}

    crm_set = _get_crm_accounts(db)
    acc_type = "crm" if target_user in crm_set else "normal"

    try:
        uids = doveadm.search_uids(target_user, folder=folder_name, unseen=unread, limit=page_size)
        headers = doveadm.fetch_headers(target_user, uids, folder=folder_name)
    except Exception as e:
        headers = []

    conversations = []
    for h in headers:
        conversations.append({
            "id": h.get("uid"),
            "subject": h.get("subject"),
            "from": {"name": "", "email": h.get("from", "")},
            "date": h.get("date"),
            "read": h.get("read", False),
            "account": {
                "id": target_user,
                "email": target_user,
                "type": acc_type
            },
            "folderId": folder,
            "hasAttachments": False,  # TODO: enhance with body structure
            "to": h.get("to"),
            "cc": h.get("cc"),
        })

    return {
        "count": len(conversations),
        "conversations": conversations,
        "filters_applied": {
            "folder": folder,
            "accountId": accountId,
            "unread": unread,
        }
    }

@app.get("/api/v1/mail/conversation/{conv_id}.json")
def get_conversation(conv_id: int, accountId: Optional[str] = Query(None), loadAll: bool = False, token_info=Depends(verify_token), db=Depends(get_db)):
    """
    Message detail. Returns body parts (best effort via doveadm).
    For full MIME/attachments we can extend to parse raw message.
    """
    if not accountId:
        return {"id": conv_id, "error": "accountId required for now"}

    crm_set = _get_crm_accounts(db)
    acc_type = "crm" if accountId in crm_set else "normal"

    try:
        body = doveadm.fetch_body(accountId, conv_id)
    except Exception:
        body = {"textBody": "", "htmlBody": "", "attachments": []}

    return {
        "id": conv_id,
        "subject": "(loaded)",
        "account": {"id": accountId, "email": accountId, "type": acc_type},
        "messages": [
            {
                "id": conv_id,
                "from": {"name": "", "email": ""},
                "date": "",
                "htmlBody": body.get("htmlBody", ""),
                "textBody": body.get("textBody", ""),
                "attachments": body.get("attachments", []),
            }
        ]
    }

@app.put("/api/v1/mail/conversations/mark.json")
async def mark_conversations(
    ids: List[str] = Query(..., alias="ids[]"),
    status: str = Query(..., description="read or unread"),
    accountId: Optional[str] = Query(None),
    token_info=Depends(verify_token),
):
    """Mark conversations/messages as read or unread. Matches dashboard usage."""
    if not accountId:
        raise HTTPException(400, "accountId is required")
    uids = [int(x) for x in ids if x.strip().isdigit()]
    seen = (status.lower() == "read")
    ok = doveadm.set_flag(accountId, uids, flag="\\Seen", add=seen)
    return {"success": ok, "marked": len(uids), "status": status}


@app.put("/api/v1/mail/conversations/move.json")
async def move_conversations(
    ids: List[str] = Query(..., alias="ids[]"),
    folder: int = Query(4),
    accountId: Optional[str] = Query(None),
    token_info=Depends(verify_token),
):
    """Move to folder (e.g. folder=4 for Trash)."""
    if not accountId:
        raise HTTPException(400, "accountId is required")
    dest = FOLDER_MAP.get(folder, "Trash")
    uids = [int(x) for x in ids if x.strip().isdigit()]
    ok = doveadm.move_messages(accountId, uids, dest_folder=dest)
    return {"success": ok, "moved": len(uids), "to_folder": dest}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("ROBUST_MAIL_API_PORT", "8090")))
