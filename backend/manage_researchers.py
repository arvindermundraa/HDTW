"""Manage LLHS researcher accounts from the server shell — mainly to create
the first admin, after which admins can add staff from /research-admin.

    python manage_researchers.py add staff@tamu.edu --name "Jane Doe" --admin
    python manage_researchers.py list
    python manage_researchers.py disable staff@tamu.edu
    python manage_researchers.py enable staff@tamu.edu
    python manage_researchers.py reset-password staff@tamu.edu

Passwords are prompted for (never passed on the command line) and stored
bcrypt-hashed, the same way server.py hashes them. Reads MONGO_URL/DB_NAME
from the environment or backend/.env.
"""
import argparse
import getpass
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import bcrypt
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).parent / ".env")
import os  # noqa: E402

MIN_PASSWORD = 10


def _db():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _hash(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def _prompt_password() -> str:
    pw = getpass.getpass("Password (min 10 chars): ")
    if len(pw) < MIN_PASSWORD:
        sys.exit("Password too short.")
    if getpass.getpass("Repeat password: ") != pw:
        sys.exit("Passwords don't match.")
    return pw


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    add = sub.add_parser("add")
    add.add_argument("email")
    add.add_argument("--name", default="")
    add.add_argument("--admin", action="store_true")
    sub.add_parser("list")
    for name in ("disable", "enable", "reset-password"):
        sub.add_parser(name).add_argument("email")
    args = ap.parse_args()

    col = _db().researchers
    if args.cmd == "list":
        for r in col.find({}, {"_id": 0, "password": 0}):
            print(f"{r['email']:<35} {r.get('role', 'staff'):<6} {'active' if r.get('active', True) else 'DISABLED'}")
        return

    email = args.email.strip().lower()
    if args.cmd == "add":
        if col.find_one({"email": email}):
            sys.exit(f"{email} already exists.")
        col.insert_one({
            "id": str(uuid.uuid4()), "email": email, "name": args.name or email.split("@")[0],
            "password": _hash(_prompt_password()), "role": "admin" if args.admin else "staff",
            "active": True, "created_at": datetime.now(timezone.utc).isoformat(), "created_by": "manage_researchers.py",
        })
        print(f"Created {'admin' if args.admin else 'staff'} researcher {email}.")
        return

    update = {"disable": {"active": False}, "enable": {"active": True}}.get(args.cmd)
    if args.cmd == "reset-password":
        update = {"password": _hash(_prompt_password())}
    if not col.update_one({"email": email}, {"$set": update}).matched_count:
        sys.exit(f"No researcher {email}.")
    print(f"{args.cmd} done for {email}.")


if __name__ == "__main__":
    main()
