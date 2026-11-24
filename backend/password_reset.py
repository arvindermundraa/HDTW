"""
Forgot password: a 6-digit code emailed to the account's address, then a new
password. Codes are stored hashed and bound to the email they were sent to,
expire after CODE_TTL_MINUTES and allow CODE_MAX_ATTEMPTS guesses.

Email goes out through mailer.py (SMTP). Pure helpers plus the sender; the
routes live in server.py.
"""
import hashlib
import hmac
import secrets

import mailer

CODE_TTL_MINUTES = 15
CODE_MAX_ATTEMPTS = 5
CODE_RESEND_SECONDS = 60


def new_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_code(email: str, code: str, secret: str) -> str:
    return hmac.new(secret.encode(), f"reset:{email.strip().lower()}:{code.strip()}".encode(), hashlib.sha256).hexdigest()


def codes_match(stored_hash: str, email: str, code: str, secret: str) -> bool:
    return hmac.compare_digest(stored_hash, hash_code(email, code, secret))


def email_configured() -> bool:
    return mailer.configured()


def send_reset_email(to: str, code: str) -> None:
    """Blocking SMTP send; call it from a thread."""
    mailer.send(
        to,
        f"Your LLHS password reset code: {code}",
        f"Your LLHS password reset code is {code}.\n\n"
        f"Enter it in the app to choose a new password. It expires in {CODE_TTL_MINUTES} minutes.\n\n"
        "If you didn't ask to reset your password, you can ignore this email; your password stays the same.",
    )
