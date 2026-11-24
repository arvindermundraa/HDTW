"""Unit tests for password_reset.py helpers. No server or database."""
import password_reset as pr


def test_codes_are_six_digits():
    for _ in range(50):
        code = pr.new_code()
        assert len(code) == 6 and code.isdigit()


def test_code_is_bound_to_email_and_secret():
    h = pr.hash_code("maya@tamu.edu", "123456", "secret")
    assert pr.codes_match(h, "MAYA@tamu.edu ", " 123456", "secret")
    assert not pr.codes_match(h, "sam@tamu.edu", "123456", "secret")
    assert not pr.codes_match(h, "maya@tamu.edu", "123457", "secret")
    assert not pr.codes_match(h, "maya@tamu.edu", "123456", "other-secret")


def test_email_configured_needs_host_and_sender(monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("EMAIL_FROM", raising=False)
    assert not pr.email_configured()
    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    assert not pr.email_configured()
    monkeypatch.setenv("EMAIL_FROM", "LLHS Study <study@example.com>")
    assert pr.email_configured()
