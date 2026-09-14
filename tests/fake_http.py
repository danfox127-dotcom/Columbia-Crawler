"""Fake HTTP session for crawler tests — serves a canned link graph.

Tracks request order, headers, and peak concurrency so tests can assert on
parallelism and conditional-request behaviour without touching the network.
"""

import threading
import time


class FakeResponse:
    def __init__(self, url, status_code, headers, text, history_urls=()):
        self.url = url
        self.status_code = status_code
        self.headers = headers
        self.text = text
        self.history = [
            type("R", (), {"url": u, "status_code": 301})() for u in history_urls
        ]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def page(links=(), status=200, etag=None, last_modified=None, gate=None, always_304=False):
    """Spec for one fake page. `gate` is a threading.Event the request waits on."""
    body = "".join(f'<a href="{href}">x</a>' for href in links)
    return {
        "html": f"<html><head><title>t</title></head><body>{body}</body></html>",
        "status": status,
        "etag": etag,
        "last_modified": last_modified,
        "gate": gate,
        "always_304": always_304,
    }


class FakeSite:
    """Stands in for requests.Session.get."""

    def __init__(self, pages, latency=0.0):
        self.pages = pages
        self.latency = latency
        self.lock = threading.Lock()
        self.requests = []          # list of (url, headers dict)
        self._in_flight = 0
        self.max_in_flight = 0

    # ── introspection helpers ───────────────────────────────────────────────
    @property
    def urls_requested(self):
        with self.lock:
            return [u for u, _ in self.requests]

    def headers_for(self, url):
        with self.lock:
            return [h for u, h in self.requests if u == url]

    # ── the session.get stand-in ────────────────────────────────────────────
    def get(self, url, headers=None, **kwargs):
        with self.lock:
            self.requests.append((url, dict(headers or {})))
            self._in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self._in_flight)
        try:
            spec = self.pages.get(url)
            if spec is None:
                return FakeResponse(url, 404, {"content-type": "text/html"}, "")

            if spec.get("gate") is not None:
                spec["gate"].wait(timeout=5)
            if self.latency:
                time.sleep(self.latency)

            if spec.get("always_304"):
                return FakeResponse(url, 304, {}, "")

            sent = dict(headers or {})
            if spec.get("etag") and sent.get("If-None-Match") == spec["etag"]:
                return FakeResponse(url, 304, {}, "")
            if spec.get("last_modified") and sent.get("If-Modified-Since") == spec["last_modified"]:
                return FakeResponse(url, 304, {}, "")

            resp_headers = {"content-type": "text/html; charset=utf-8"}
            if spec.get("etag"):
                resp_headers["ETag"] = spec["etag"]
            if spec.get("last_modified"):
                resp_headers["Last-Modified"] = spec["last_modified"]
            return FakeResponse(url, spec["status"], resp_headers, spec["html"])
        finally:
            with self.lock:
                self._in_flight -= 1
