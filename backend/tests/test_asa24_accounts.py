"""Unit tests for asa24_accounts.parse_accounts: reading the ASA24 account
list staff paste on /research-admin. No server or database."""
import pytest

import asa24_accounts as acc


def test_parse_accounts_with_and_without_header():
    rows = acc.parse_accounts("username,password\nLLHS0001,pa55\nllhs0002, w0rd \n\n")
    assert rows == [{"username": "llhs0001", "password": "pa55"}, {"username": "llhs0002", "password": "w0rd"}]
    assert acc.parse_accounts("llhs0003,x")[0]["username"] == "llhs0003"


@pytest.mark.parametrize("text,msg", [
    ("llhs0001", "needs a username and a password"),
    ("llhs0001,a\nllhs0001,b", "appears twice"),
    ("   ", "No accounts found"),
])
def test_parse_accounts_rejects_bad_lists(text, msg):
    with pytest.raises(acc.AccountsFileError, match=msg):
        acc.parse_accounts(text)
