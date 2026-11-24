"""
Create account: anyone with an email at ALLOWED_EMAIL_DOMAIN (default
tamu.edu) can create an LLHS account, after proving the address with a
6-digit code emailed to it. Codes are stored hashed and bound to the email,
expire after CODE_TTL_MINUTES and allow CODE_MAX_ATTEMPTS guesses.
Pure helpers plus the sender; the routes live in server.py.
"""
import hashlib
import hmac
import os
import secrets

import mailer

CODE_TTL_MINUTES = 15
CODE_MAX_ATTEMPTS = 5
CODE_RESEND_SECONDS = 60


def allowed_domain() -> str:
    return os.environ.get("ALLOWED_EMAIL_DOMAIN", "tamu.edu").strip().lower().lstrip("@")


def email_allowed(email: str, domain: str = None) -> bool:
    """Exact domain only: x@tamu.edu yes; x@nottamu.edu and x@tamu.edu.evil.com no."""
    domain = allowed_domain() if domain is None else domain
    return email.strip().lower().rsplit("@", 1)[-1] == domain


def new_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_code(email: str, code: str, secret: str) -> str:
    return hmac.new(secret.encode(), f"signup:{email.strip().lower()}:{code.strip()}".encode(), hashlib.sha256).hexdigest()


def codes_match(stored_hash: str, email: str, code: str, secret: str) -> bool:
    return hmac.compare_digest(stored_hash, hash_code(email, code, secret))


def send_signup_email(to: str, code: str) -> None:
    """Blocking SMTP send; call it from a thread."""
    mailer.send(
        to,
        f"Your LLHS sign-up code: {code}",
        f"Your LLHS sign-up code is {code}.\n\n"
        f"Enter it in the app to finish creating your account. It expires in {CODE_TTL_MINUTES} minutes.\n\n"
        "If you didn't ask to create an LLHS account, you can ignore this email.",
    )
