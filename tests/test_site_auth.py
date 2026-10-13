"""HTTP Basic credentials go only to the audited site, and only over HTTPS."""

import base64

import requests

from crawler import Crawler, SiteBasicAuth

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
