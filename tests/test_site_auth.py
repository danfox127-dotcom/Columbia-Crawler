"""HTTP Basic credentials go only to the audited site, and only over HTTPS."""

import base64

import requests

from crawler import Crawler, SiteBasicAuth, resolve_site_creds

CREDS = ("editor", "s3cret")
EXPECTED = "Basic " + base64.b64encode(b"editor:s3cret").decode()


def _auth_header(auth, url):
    prepared = requests.Request("GET", url).prepare()
    return auth(prepared).headers.get("Authorization")


def test_credentials_sent_to_the_site_host():
    auth = SiteBasicAuth("https://www.example.com", *CREDS)
    assert _auth_header(auth, "https://www.example.com/private/page") == EXPECTED


def test_credentials_sent_to_www_and_bare_host_alike():
    auth = SiteBasicAuth("https://example.com", *CREDS)
    assert _auth_header(auth, "https://www.example.com/x") == EXPECTED


def test_credentials_not_sent_to_other_hosts():
    auth = SiteBasicAuth("https://example.com", *CREDS)
    assert _auth_header(auth, "https://cdn.other.com/x") is None
    assert _auth_header(auth, "https://evil-example.com/x") is None


def test_credentials_not_sent_over_plain_http():
    auth = SiteBasicAuth("https://example.com", *CREDS)
    assert _auth_header(auth, "http://example.com/x") is None


def test_crawler_uses_site_auth_when_given_credentials():
    c = Crawler("https://example.com", respect_robots=False, auth=CREDS)
    assert isinstance(c.session.auth, SiteBasicAuth)
    assert _auth_header(c.session.auth, "https://example.com/p") == EXPECTED


def test_crawler_without_credentials_sends_no_auth():
    c = Crawler("https://example.com", respect_robots=False)
    assert c.session.auth is None


def test_blank_credentials_are_ignored():
    c = Crawler("https://example.com", respect_robots=False, auth=("", ""))
    assert c.session.auth is None


# ── which login a run uses ──────────────────────────────────────────────────

SAVED = {
    "SITE_AUTH_USER": "saved-user",
    "SITE_AUTH_PASSWORD": "saved-pass",
    "SITE_AUTH_HOST": "www.columbiadoctors.org",
}


def test_saved_login_used_for_its_own_site():
    got = resolve_site_creds("https://columbiadoctors.org/sitemap.xml", "", "", SAVED)
    assert got == ("saved-user", "saved-pass")


def test_saved_login_never_sent_to_a_visitor_chosen_site():
    assert resolve_site_creds("https://attacker.example/", "", "", SAVED) is None
    assert resolve_site_creds("https://columbiadoctors.org.attacker.example/", "", "", SAVED) is None


def test_saved_login_unused_without_a_saved_host():
    env = {k: v for k, v in SAVED.items() if k != "SITE_AUTH_HOST"}
    assert resolve_site_creds("https://www.columbiadoctors.org/", "", "", env) is None


def test_saved_host_may_be_given_as_a_url():
    env = dict(SAVED, SITE_AUTH_HOST="https://www.columbiadoctors.org/")
    assert resolve_site_creds("https://www.columbiadoctors.org/x", "", "", env) is not None


def test_typed_login_goes_to_whatever_site_the_user_chose():
    got = resolve_site_creds("https://other.example/", "me", "pw", SAVED)
    assert got == ("me", "pw")


def test_half_typed_login_never_borrows_the_saved_password():
    assert resolve_site_creds("https://attacker.example/", "me", "", SAVED) is None
    assert resolve_site_creds("https://www.columbiadoctors.org/", "me", "", SAVED) is None
