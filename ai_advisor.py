"""
ai_advisor.py — AI-powered SEO copy generation.
Supports both Claude (Anthropic) and Gemini (Google) as providers.
"""

import base64
from typing import Optional

import requests as req


# ── Shared helpers ───────────────────────────────────────────────────────────

_FETCH_HEADERS = {"User-Agent": "ContentCT/1.0 SEO Audit"}


def _fetch_image(image_url: str):
    """Download an image, return (bytes, content_type) or raise."""
    resp = req.get(image_url, timeout=10, headers=_FETCH_HEADERS)
    resp.raise_for_status()
    ct = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
    if not ct.startswith("image/"):
        raise ValueError(f"Not an image: {ct}")
    return resp.content, ct


def _alt_prompt(page_context: str = "") -> str:
    context_line = f"\nPage context: {page_context[:200]}" if page_context else ""
    return (
        f"Write alt text for this image.{context_line}\n\n"
        "Rules:\n"
        "- Describe what the image shows, not what it means\n"
        "- Be specific (who/what/where if apparent)\n"
        "- Under 125 characters\n"
        "- Do not start with 'Image of' or 'Photo of'\n\n"
        "Reply with ONLY the alt text — no quotes, no explanation."
    )


def _meta_prompt(url: str, title: str, h1: str, content_snippet: str) -> str:
    return (
        "Write a meta description for this webpage.\n\n"
        f"URL: {url}\n"
        f"Title tag: {title}\n"
        f"H1: {h1}\n"
        f"Content: {content_snippet[:400]}\n\n"
        "Requirements:\n"
        "- 120–155 characters\n"
        "- Include the primary topic keyword naturally\n"
        "- Compelling, encourages clicks\n"
        "- Active voice\n"
        "- No quotes or special characters\n\n"
        "Reply with ONLY the meta description text, nothing else."
    )


def _title_prompt(url: str, h1: str, content_snippet: str) -> str:
    return (
        "Write an SEO title tag for this webpage.\n\n"
        f"URL: {url}\n"
        f"H1: {h1}\n"
        f"Content: {content_snippet[:300]}\n\n"
        "Requirements:\n"
        "- 40–60 characters\n"
        "- Primary keyword near the front\n"
        "- Descriptive and compelling\n\n"
        "Reply with ONLY the title text, nothing else."
    )


def _clean(text: str) -> str:
    return text.strip().strip("\"'")


# ── Claude (Anthropic) ──────────────────────────────────────────────────────

class ClaudeAdvisor:
    """Uses claude-haiku-4-5 — fast and cheap for bulk audits."""

    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001"):
        import anthropic
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def generate_alt_text(self, image_url: str, page_context: str = "") -> str:
        try:
            img_bytes, ct = _fetch_image(image_url)
            b64 = base64.standard_b64encode(img_bytes).decode()
        except Exception as exc:
            return f"(could not fetch image: {str(exc)[:50]})"

        try:
            msg = self.client.messages.create(
                model=self.model,
                max_tokens=150,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {
                            "type": "base64", "media_type": ct, "data": b64}},
                        {"type": "text", "text": _alt_prompt(page_context)},
                    ],
                }],
            )
            return _clean(msg.content[0].text)
        except Exception as exc:
            return f"(AI error: {str(exc)[:60]})"

    def draft_meta_description(self, url, title, h1, content_snippet) -> str:
        try:
            msg = self.client.messages.create(
                model=self.model,
                max_tokens=200,
                messages=[{"role": "user",
                           "content": _meta_prompt(url, title, h1, content_snippet)}],
            )
            result = _clean(msg.content[0].text)
            return result[:160] if len(result) > 160 else result
        except Exception as exc:
            return f"(AI error: {str(exc)[:60]})"

    def draft_title(self, url, h1, content_snippet) -> str:
        try:
            msg = self.client.messages.create(
                model=self.model,
                max_tokens=100,
                messages=[{"role": "user",
                           "content": _title_prompt(url, h1, content_snippet)}],
            )
            return _clean(msg.content[0].text)
        except Exception as exc:
            return f"(AI error: {str(exc)[:60]})"


# ── Gemini (Google) ──────────────────────────────────────────────────────────

class GeminiAdvisor:
    """Uses gemini-2.5-flash — very cheap, great for high-volume audits."""

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash-preview-05-20"):
        from google import genai
        self.client = genai.Client(api_key=api_key)
        self.model_name = model

    def generate_alt_text(self, image_url: str, page_context: str = "") -> str:
        try:
            img_bytes, ct = _fetch_image(image_url)
        except Exception as exc:
            return f"(could not fetch image: {str(exc)[:50]})"

        try:
            from google.genai import types
            resp = self.client.models.generate_content(
                model=self.model_name,
                contents=[
                    types.Part.from_bytes(data=img_bytes, mime_type=ct),
                    _alt_prompt(page_context),
                ],
            )
            return _clean(resp.text)
        except Exception as exc:
            return f"(AI error: {str(exc)[:60]})"

    def draft_meta_description(self, url, title, h1, content_snippet) -> str:
        try:
            resp = self.client.models.generate_content(
                model=self.model_name,
                contents=_meta_prompt(url, title, h1, content_snippet),
            )
            result = _clean(resp.text)
            return result[:160] if len(result) > 160 else result
        except Exception as exc:
            return f"(AI error: {str(exc)[:60]})"

    def draft_title(self, url, h1, content_snippet) -> str:
        try:
            resp = self.client.models.generate_content(
                model=self.model_name,
                contents=_title_prompt(url, h1, content_snippet),
            )
            return _clean(resp.text)
        except Exception as exc:
            return f"(AI error: {str(exc)[:60]})"


# ── Factory ──────────────────────────────────────────────────────────────────

def create_advisor(provider: str, api_key: str):
    """Return the right advisor for the chosen provider."""
    if provider == "Gemini":
        return GeminiAdvisor(api_key)
    return ClaudeAdvisor(api_key)
