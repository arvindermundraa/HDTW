"""Unit tests for signup.py helpers. No server or database."""
import signup


def test_only_the_exact_domain_is_allowed():
    assert signup.email_allowed("Maya.Lee@TAMU.edu", "tamu.edu")
    assert not signup.email_allowed("maya@nottamu.edu", "tamu.edu")
    assert not signup.email_allowed("maya@tamu.edu.evil.com", "tamu.edu")
    assert not signup.email_allowed("maya@gmail.com", "tamu.edu")


def test_default_domain_is_tamu(monkeypatch):
    monkeypatch.delenv("ALLOWED_EMAIL_DOMAIN", raising=False)
    assert signup.allowed_domain() == "tamu.edu"
    monkeypatch.setenv("ALLOWED_EMAIL_DOMAIN", "@Example.org")
    assert signup.allowed_domain() == "example.org"


def test_signup_codes_are_separate_from_reset_codes():
    import password_reset
    h = signup.hash_code("maya@tamu.edu", "123456", "secret")
    assert signup.codes_match(h, "MAYA@tamu.edu", " 123456 ", "secret")
    assert not signup.codes_match(h, "sam@tamu.edu", "123456", "secret")
    # a password-reset code for the same email can't be used to sign up
    assert h != password_reset.hash_code("maya@tamu.edu", "123456", "secret")
