"""
Reads the ASA24 respondent accounts staff paste on /research-admin, one
"username,password" per line, as created on the ASA24 researcher site.
Participants are given the next free account; the username (e.g. llhs0042)
is the only thing that links ASA24 data to a person, so no names or emails
ever go to ASA24. Pure function; the routes live in server.py.
"""
import csv
import io
from typing import Dict, List


class AccountsFileError(ValueError):
    """The pasted ASA24 account list can't be read. Message is safe to show staff."""


def parse_accounts(text: str) -> List[Dict[str, str]]:
    """Reads "username,password" lines (a header row is optional).
    Usernames are lower-cased."""
    rows = [r for r in csv.reader(io.StringIO(text.strip().lstrip("﻿"))) if any(c.strip() for c in r)]
    if rows and rows[0] and rows[0][0].strip().lower() in ("username", "user name", "user"):
        rows = rows[1:]
    out, seen = [], set()
    for n, r in enumerate(rows, start=1):
        if len(r) < 2 or not r[0].strip() or not r[1].strip():
            raise AccountsFileError(f"Line {n} needs a username and a password, separated by a comma.")
        username = r[0].strip().lower()
        if username in seen:
            raise AccountsFileError(f"Username {username} appears twice.")
        seen.add(username)
        out.append({"username": username, "password": r[1].strip()})
    if not out:
        raise AccountsFileError("No accounts found. Paste one 'username,password' per line.")
    return out
