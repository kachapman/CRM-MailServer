"""
crm_mail_api.doveadm
Wrapper around doveadm for reliable access to mail data (flags for read/unread,
search, folders, mark, move).

Designed to work with the Dovecot in this ONLYOFFICE MailServer image.
Uses JSON output where possible.
"""

import subprocess
import json
import os
from typing import List, Dict, Any, Optional, Tuple

DOVEADM_BIN = os.getenv("DOVEADM_BIN", "/usr/bin/doveadm")


def _run(cmd: List[str], user: Optional[str] = None, json_fmt: bool = True) -> Any:
    """Run doveadm command. Returns parsed JSON or raw text."""
    full = [DOVEADM_BIN]
    if json_fmt:
        full += ["-f", "json"]
    if user:
        full += ["-u", user]
    full += cmd

    result = subprocess.run(full, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"doveadm {' '.join(cmd)} failed: {stderr}")

    out = result.stdout.strip()
    if not out:
        return [] if json_fmt else ""

    if json_fmt:
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            # Fallback: some commands may not be pure json array
            return out
    return out


def list_folders(user: str) -> List[Dict[str, Any]]:
    """Return list of folders for the user."""
    try:
        data = _run(["mailbox", "list"], user=user)
        # Normalize to list of dicts with name
        if isinstance(data, list):
            folders = []
            for item in data:
                if isinstance(item, dict):
                    folders.append({"name": item.get("name") or item.get("mailbox", "INBOX")})
                else:
                    folders.append({"name": str(item)})
            return folders
        return [{"name": "INBOX"}]
    except Exception:
        return [{"name": "INBOX"}]


def search_uids(user: str, folder: str = "INBOX", unseen: Optional[bool] = None,
                limit: int = 100) -> List[int]:
    """Return list of UIDs matching criteria."""
    cmd = ["search"]
    if unseen is True:
        cmd.append("UNSEEN")
    elif unseen is False:
        cmd.append("SEEN")
    cmd += ["mailbox", folder]

    try:
        data = _run(cmd, user=user)
        uids = []
        if isinstance(data, list):
            for row in data:
                if isinstance(row, dict) and "uid" in row:
                    uids.append(int(row["uid"]))
                elif isinstance(row, (int, str)):
                    uids.append(int(row))
        return uids[:limit]
    except Exception:
        return []


def fetch_headers(user: str, uids: List[int], folder: str = "INBOX") -> List[Dict[str, Any]]:
    """Fetch basic headers + flags for given UIDs."""
    if not uids:
        return []
    uid_list = ",".join(str(u) for u in uids)
    cmd = ["fetch", "uid", "flags", "hdr.subject", "hdr.from", "hdr.date", "hdr.to", "hdr.cc",
           "mailbox", folder, "uid", uid_list]
    try:
        rows = _run(cmd, user=user) or []
        results = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            flags = r.get("flags", []) or []
            is_read = "\\Seen" in flags or "Seen" in str(flags)
            results.append({
                "uid": r.get("uid"),
                "flags": flags,
                "read": is_read,
                "subject": r.get("hdr.subject") or r.get("subject") or "(no subject)",
                "from": r.get("hdr.from") or "",
                "date": r.get("hdr.date") or "",
                "to": r.get("hdr.to") or "",
                "cc": r.get("hdr.cc") or "",
            })
        return results
    except Exception as e:
        # Fallback empty
        return []


def set_flag(user: str, uids: List[int], flag: str = "\\Seen", add: bool = True, folder: str = "INBOX") -> bool:
    """Add or remove a flag (e.g. \\Seen for read/unread)."""
    if not uids:
        return True
    uid_str = ",".join(str(u) for u in uids)
    action = "add" if add else "remove"
    cmd = ["flags", action, flag, "mailbox", folder, "uid", uid_str]
    try:
        _run(cmd, user=user, json_fmt=False)
        return True
    except Exception:
        return False


def move_messages(user: str, uids: List[int], dest_folder: str, src_folder: str = "INBOX") -> bool:
    if not uids:
        return True
    uid_str = ",".join(str(u) for u in uids)
    cmd = ["move", dest_folder, "mailbox", src_folder, "uid", uid_str]
    try:
        _run(cmd, user=user, json_fmt=False)
        return True
    except Exception:
        return False


def fetch_body(user: str, uid: int, folder: str = "INBOX") -> Dict[str, Any]:
    """Fetch text/html body parts for a message. Best effort."""
    cmd = ["fetch", "text", "body", "mailbox", folder, "uid", str(uid)]
    try:
        data = _run(cmd, user=user) or []
        text = ""
        html = ""
        if isinstance(data, list) and data:
            item = data[0] if isinstance(data[0], dict) else {}
            # doveadm may return 'text' or 'body'
            text = item.get("text") or item.get("body") or ""
            html = item.get("html") or ""
        return {"textBody": text, "htmlBody": html, "attachments": []}
    except Exception:
        return {"textBody": "", "htmlBody": "", "attachments": []}


def get_raw_message(user: str, uid: int, folder: str = "INBOX") -> bytes:
    """Attempt to fetch the raw message. Falls back to empty."""
    # doveadm doesn't have direct raw easily in old versions; use fetch 'body' + reconstruct or read maildir.
    # For v1 we return headers+body from fetch.
    # Real raw can be added later via maildir lookup or IMAP.
    return b""
