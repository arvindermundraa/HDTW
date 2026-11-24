"""
Sends the app's few emails (sign-up and password-reset codes) over SMTP, e.g.
a study Gmail with an app password: SMTP_HOST=smtp.gmail.com, SMTP_PORT=465,
SMTP_USER, SMTP_PASSWORD, EMAIL_FROM.
"""
import os
import smtplib
import ssl
from email.message import EmailMessage


def configured() -> bool:
    return bool(os.environ.get("SMTP_HOST") and os.environ.get("EMAIL_FROM"))


def send(to: str, subject: str, body: str) -> None:
    """Blocking SMTP send; call it from a thread."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.environ["EMAIL_FROM"]
    msg["To"] = to
    msg.set_content(body)
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "465"))
    user, password = os.environ.get("SMTP_USER", ""), os.environ.get("SMTP_PASSWORD", "")
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=20) as s:
            if user:
                s.login(user, password)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=20) as s:
            s.starttls(context=ssl.create_default_context())
            if user:
                s.login(user, password)
            s.send_message(msg)
