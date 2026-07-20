#!/usr/bin/env python
"""
tools/create_crm_mail_account.py

Helper to create a receive-only "CRM Mail" / universal record inbox account.

This marks the account so the robust mail API (crm_mail_api) knows to surface
it with type="crm" and enables filtering by account in external apps.

It does NOT automatically configure delivery. Users must set up:
- Postfix aliases / virtual maps, or
- Sieve rules (fileinto or redirect :copy), or
- Sender-side BCC to this address.

Usage (inside container or with DB access):
  python tools/create_crm_mail_account.py crm@yourdomain.com "CRM Record Inbox"

The script reuses the same DB and maildir hashing logic as create_mailboxes.py
where possible.
"""

import os
import sys
import datetime
import crypt
import getpass

try:
    import mysql.connector
except ImportError:
    print("mysql-connector-python required. pip install mysql-connector-python")
    sys.exit(1)

DB_HOST = os.getenv("MAIL_SERVER_DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("MAIL_SERVER_DB_PORT", "3306"))
DB_NAME = os.getenv("MAIL_SERVER_DB_NAME", "onlyoffice_mailserver")
DB_USER = os.getenv("MAIL_SERVER_DB_USER", "root")
DB_PASS = os.getenv("MAIL_SERVER_DB_PASS", os.getenv("MYSQL_ROOT_PASSWD", "Isadmin123"))

STORAGE_BASE = os.getenv("STORAGE_BASE_DIR", "/var/vmail")
STORAGE_NODE = "vmail1"


def hash_maildir(local_part: str, domain: str) -> str:
    """Simple 3-level hash matching the style in create_mailboxes.py"""
    now = datetime.datetime.utcnow().strftime("%Y.%m.%d.%H.%M.%S")
    if len(local_part) == 1:
        return f"{domain}/{local_part[0]}/{local_part}-{now}/"
    elif len(local_part) == 2:
        return f"{domain}/{local_part[0]}/{local_part[1]}/{local_part}-{now}/"
    else:
        return f"{domain}/{local_part[0]}/{local_part[1]}/{local_part[2]}/{local_part}-{now}/"


def main():
    if len(sys.argv) < 2:
        print("Usage: python create_crm_mail_account.py <email> [display-name]")
        print("Example: python create_crm_mail_account.py crm@vanguardadj.online 'CRM Record Inbox'")
        sys.exit(1)

    email = sys.argv[1].lower().strip()
    display = sys.argv[2] if len(sys.argv) > 2 else email.split("@")[0]

    if "@" not in email:
        print("ERROR: email must contain @")
        sys.exit(1)

    local_part, domain = email.split("@", 1)

    print(f"Creating CRM Mail account: {email}")
    password = getpass.getpass("Enter password for the account (will be hashed): ")

    encrypted = crypt.crypt(password, crypt.mksalt(crypt.METHOD_SHA512))
    maildir = hash_maildir(local_part, domain)

    conn = mysql.connector.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS, database=DB_NAME
    )
    cur = conn.cursor()

    # Ensure domain exists (basic)
    cur.execute("SELECT domain FROM domain WHERE domain=%s", (domain,))
    if not cur.fetchone():
        print(f"WARNING: domain {domain} does not exist in the domain table.")
        print("Create it first via legacy API or direct INSERT if needed.")

    now = datetime.datetime.utcnow()

    # Insert mailbox if not exists (minimal columns for compatibility)
    try:
        cur.execute(
            """
            INSERT INTO mailbox (
                username, password, name, language, maildir, domain,
                storagebasedirectory, storagenode,
                quota, active, local_part, created, modified,
                enablesmtp, enableimap, enablepop3, enabledeliver,
                enablesieve, enablemanagesieve
            ) VALUES (
                %s, %s, %s, 'en_US', %s, %s,
                %s, %s,
                0, 1, %s, %s, %s,
                0, 1, 0, 1,
                1, 1
            )
            """,
            (
                email, encrypted, display, maildir, domain,
                STORAGE_BASE, STORAGE_NODE,
                local_part, now, now,
            ),
        )
        print("  mailbox row inserted")
    except mysql.connector.IntegrityError:
        print("  mailbox already exists (continuing)")

    # Insert alias (goto self)
    try:
        cur.execute(
            """
            INSERT INTO alias (address, goto, name, domain, active, created, modified, expired)
            VALUES (%s, %s, %s, %s, 1, %s, %s, '9999-12-31 00:00:00')
            """,
            (email, email, display, domain, now, now),
        )
        print("  alias row inserted")
    except mysql.connector.IntegrityError:
        print("  alias already exists (continuing)")

    # Mark as CRM mail account (new table or settings)
    # For simplicity we use a dedicated table if present, else fall back to settings text.
    try:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS crm_mail_accounts (
                username VARCHAR(255) PRIMARY KEY,
                type VARCHAR(32) NOT NULL DEFAULT 'crm',
                description TEXT,
                created DATETIME,
                modified DATETIME
            ) ENGINE=InnoDB
            """
        )
        cur.execute(
            """
            INSERT INTO crm_mail_accounts (username, type, description, created, modified)
            VALUES (%s, 'crm', %s, %s, %s)
            ON DUPLICATE KEY UPDATE type='crm', description=VALUES(description), modified=VALUES(modified)
            """,
            (email, display, now, now),
        )
        print("  crm_mail_accounts marker set (type=crm)")
    except Exception as e:
        print(f"  (non-fatal) could not create crm_mail_accounts marker: {e}")

    conn.commit()
    cur.close()
    conn.close()

    # Create maildir skeleton (best effort)
    try:
        full_maildir = os.path.join(STORAGE_BASE, "vmail1", maildir)
        for sub in ("tmp", "new", "cur"):
            os.makedirs(os.path.join(full_maildir, sub), exist_ok=True)
        # Permissions similar to vmail user (2000)
        os.chmod(full_maildir, 0o700)
        print(f"  maildir skeleton ensured at {full_maildir}")
    except Exception as e:
        print(f"  (warning) could not create maildir dirs: {e}")

    print("\nAccount created (or already present).")
    print("IMPORTANT: This is receive-only by convention.")
    print("Configure delivery yourself, e.g.:")
    print(f"  - Add to virtual alias maps or aliases: {email} -> {email}")
    print("  - Or use Sieve: require [\"copy\"]; redirect :copy \"{}\";".format(email))
    print("  - Or BCC from your sending MTA / app.")
    print(f"\nMaildir will be under: {STORAGE_BASE}/vmail1/{maildir}")
    print("The robust mail API will now surface this with account.type = 'crm'.")


if __name__ == "__main__":
    main()
