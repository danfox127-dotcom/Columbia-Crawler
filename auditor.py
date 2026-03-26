"""
auditor.py — SEO issue detection. Takes a list of PageData objects,
returns a list of Issue objects, one per problem found.
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd

# ── Issue definition ────────────────────────────────────────────────────────

SEVERITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}

_FILENAME_RE = re.compile(r"\.(jpe?g|png|gif|webp|svg|bmp|tiff?)$", re.I)


@dataclass
class Issue:
    url: str
    page_title: str
    issue_type: str
    issue_label: str
    severity: str
    element: str
    current_value: str
    suggested_fix: str
    image_src: str = ""  # populated for alt-text issues so AI can fetch the image
    ai_suggested: bool = False


# issue_type → (display label, severity)
_META: Dict[str, tuple] = {
    "http_error":        ("HTTP Error (4xx/5xx)",                "Critical"),
    "missing_title":     ("Missing Title Tag",                   "Critical"),
    "duplicate_title":   ("Duplicate Title Tag",                 "High"),
    "title_too_long":    ("Title Too Long (>60 chars)",          "Medium"),
    "title_too_short":   ("Title Too Short (<30 chars)",         "Low"),
    "missing_meta":      ("Missing Meta Description",            "High"),
    "duplicate_meta":    ("Duplicate Meta Description",          "Medium"),
    "meta_too_long":     ("Meta Description Too Long (>160)",    "Medium"),
    "meta_too_short":    ("Meta Description Too Short (<70)",    "Low"),
    "missing_h1":        ("Missing H1 Tag",                      "High"),
    "multiple_h1":       ("Multiple H1 Tags",                    "Medium"),
    "missing_h2":        ("Missing H2 Tag",                      "Low"),
    "missing_alt":       ("Missing Alt Text",                    "High"),
    "empty_alt":         ("Empty Alt Text",                      "Medium"),
    "poor_alt":          ("Poor Alt Text (filename / too short)", "Medium"),
    "redirect":          ("Redirect Chain",                      "Medium"),
    "thin_content":      ("Thin Content (<300 words)",           "Medium"),
    "slow_page":         ("Slow Page Load (>3s)",                "Medium"),
    "missing_canonical": ("Missing Canonical Tag",               "Low"),
}


# ── Helpers ─────────────────────────────────────────────────────────────────

def _trunc(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def _mk(page, kind: str, element: str, current: str, fix: str, image_src: str = "") -> Issue:
    label, severity = _META[kind]
    return Issue(
        url=page.url,
        page_title=page.title or "(No Title)",
        issue_type=kind,
        issue_label=label,
        severity=severity,
        element=element,
        current_value=current,
        suggested_fix=fix,
        image_src=image_src,
    )


def _poor_alt(alt: str) -> bool:
    """Return True if existing alt text is likely useless."""
    alt = alt.strip()
    if len(alt) < 4:
        return True
    if _FILENAME_RE.search(alt):
        return True
    if alt.replace(" ", "").isdigit():
        return True
    return False


# ── Public API ───────────────────────────────────────────────────────────────

def audit(pages: list) -> List[Issue]:
    """Run all SEO checks. Returns issues sorted by severity."""
    # Build duplicate-detection maps first
    title_map: Dict[str, List[str]] = {}
    meta_map: Dict[str, List[str]] = {}
    for p in pages:
        if p.title:
            title_map.setdefault(p.title.lower(), []).append(p.url)
        if p.meta_description:
            meta_map.setdefault(p.meta_description.lower(), []).append(p.url)

    issues: List[Issue] = []
    for page in pages:
        issues.extend(_audit_page(page, title_map, meta_map))

    issues.sort(key=lambda i: SEVERITY_ORDER.get(i.severity, 99))
    return issues


def to_dataframe(issues: List[Issue]) -> pd.DataFrame:
    if not issues:
        return pd.DataFrame(
            columns=["URL", "Page Title", "Issue Type", "Severity",
                     "Element", "Current Value", "Suggested Fix", "AI Generated"]
        )
    rows = [
        {
            "URL": i.url,
            "Page Title": i.page_title,
            "Issue Type": i.issue_label,
            "Severity": i.severity,
            "Element": i.element,
            "Current Value": i.current_value,
            "Suggested Fix": i.suggested_fix,
            "AI Generated": "✓" if i.ai_suggested else "",
        }
        for i in issues
    ]
    return pd.DataFrame(rows)


# ── Per-page checks ──────────────────────────────────────────────────────────

def _audit_page(page, title_map, meta_map) -> List[Issue]:
    out: List[Issue] = []

    # HTTP errors — flag and bail; no point auditing a broken page
    if page.status_code and page.status_code >= 400:
        out.append(_mk(page, "http_error", "HTTP Status",
            str(page.status_code),
            f"Investigate the {page.status_code} error. "
            "If the page has moved, set up a 301 redirect to the new URL."))
        return out

    # ── Redirect chains ─────────────────────────────────────────────────────
    if page.is_redirect and len(page.redirect_chain) > 2:
        chain = " → ".join(page.redirect_chain[:5])
        if len(page.redirect_chain) > 5:
            chain += " …"
        out.append(_mk(page, "redirect", "Redirect Chain", chain,
            "Collapse to a single 301. Update all internal links to point "
            "directly to the final destination URL."))

    # ── Title tag ────────────────────────────────────────────────────────────
    title = page.title
    if not title:
        out.append(_mk(page, "missing_title", "<title>", "(missing)",
            "Add a <title> tag (30–60 chars). "
            "AI can draft one based on the H1 and page content."))
    else:
        tlen = len(title)
        if tlen > 60:
            out.append(_mk(page, "title_too_long", "<title>",
                f"{_trunc(title, 50)} ({tlen} chars)",
                f"Shorten to ≤60 chars (currently {tlen}). "
                "Remove the brand suffix or less-important terms from the end."))
        elif tlen < 30:
            out.append(_mk(page, "title_too_short", "<title>",
                f"{title} ({tlen} chars)",
                f"Expand to 30–60 chars (currently {tlen}). "
                "Add descriptive keywords that reflect the page topic."))

        if len(title_map.get(title.lower(), [])) > 1:
            n = len(title_map[title.lower()])
            out.append(_mk(page, "duplicate_title", "<title>", title,
                f"Same title used on {n} pages. "
                "Each page needs a unique title reflecting its specific content."))

    # ── Meta description ─────────────────────────────────────────────────────
    desc = page.meta_description
    if not desc:
        out.append(_mk(page, "missing_meta", '<meta name="description">',
            "(missing)",
            "Add a meta description (70–160 chars) summarising the page with "
            "target keywords. AI can draft this."))
    else:
        dlen = len(desc)
        if dlen > 160:
            out.append(_mk(page, "meta_too_long", '<meta name="description">',
                f"{_trunc(desc, 80)} ({dlen} chars)",
                f"Trim to ≤160 chars (currently {dlen}). "
                "Google truncates at ~155 chars."))
        elif dlen < 70:
            out.append(_mk(page, "meta_too_short", '<meta name="description">',
                f"{desc} ({dlen} chars)",
                f"Expand to 70–160 chars (currently {dlen} chars)."))

        if len(meta_map.get(desc.lower(), [])) > 1:
            n = len(meta_map[desc.lower()])
            out.append(_mk(page, "duplicate_meta", '<meta name="description">',
                _trunc(desc, 100),
                f"Same description on {n} pages. "
                "Write a unique description for each page."))

    # ── H1 ───────────────────────────────────────────────────────────────────
    if not page.h1s:
        out.append(_mk(page, "missing_h1", "<h1>", "(missing)",
            "Add exactly one H1 that clearly describes the page topic "
            "and includes the primary keyword."))
    elif len(page.h1s) > 1:
        sample = " | ".join(page.h1s[:3])
        out.append(_mk(page, "multiple_h1", "<h1>",
            f"{len(page.h1s)} H1 tags: {_trunc(sample, 80)}",
            f"Keep only one H1. Convert the others to H2 or H3."))

    # ── H2 ───────────────────────────────────────────────────────────────────
    if not page.h2s:
        out.append(_mk(page, "missing_h2", "<h2>", "(missing)",
            "Page lacks H2 subheadings. Add H2s to break up content and "
            "structure topics logically for better readability and SEO."))

    # ── Images ───────────────────────────────────────────────────────────────
    for img in page.images:
        src_label = f'<img src="{_trunc(img.src, 70)}">'
        if img.alt is None:
            out.append(_mk(page, "missing_alt", src_label,
                "(alt attribute absent)",
                "Add a descriptive alt attribute. "
                "AI can analyse the image and draft alt text.",
                image_src=img.src))
        elif img.alt.strip() == "":
            out.append(_mk(page, "empty_alt", src_label,
                'alt=""',
                "If decorative, alt=\"\" is correct. "
                "If the image conveys information, add descriptive text. "
                "AI can review the image.",
                image_src=img.src))
        elif _poor_alt(img.alt):
            out.append(_mk(page, "poor_alt", src_label,
                f'alt="{img.alt}"',
                f'Alt text "{img.alt}" looks like a filename or is too brief. '
                "AI can rewrite it.",
                image_src=img.src))

    # ── Content & performance ─────────────────────────────────────────────────
    if 0 < page.word_count < 300:
        out.append(_mk(page, "thin_content", "Body content",
            f"{page.word_count} words",
            f"Only {page.word_count} words. Expand to 300+ or consolidate with a "
            "related page if brevity is intentional."))

    if page.load_time > 3.0:
        out.append(_mk(page, "slow_page", "Page load time",
            f"{page.load_time:.2f}s",
            f"Loaded in {page.load_time:.2f}s. Check for unoptimised images, "
            "render-blocking JS/CSS, or slow server response. "
            "Run through PageSpeed Insights for detail."))

    # ── Canonical ─────────────────────────────────────────────────────────────
    if not page.canonical:
        out.append(_mk(page, "missing_canonical", '<link rel="canonical">',
            "(missing)",
            f'Add <link rel="canonical" href="{page.url}"> to the <head> '
            "to prevent duplicate-content issues."))

    return out
