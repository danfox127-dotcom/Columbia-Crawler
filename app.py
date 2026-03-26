"""
app.py — Content CT: a CAT scan for your site's content problems.
Streamlit UI wrapping crawler.py, auditor.py, and ai_advisor.py.
"""

import os

import pandas as pd
import streamlit as st

from ai_advisor import create_advisor

# ── Env-var API keys (used by HuggingFace Spaces secrets) ────────────────────
_ENV_ANTHROPIC = os.environ.get("ANTHROPIC_API_KEY", "")
_ENV_GEMINI    = os.environ.get("GOOGLE_API_KEY", "") or os.environ.get("GEMINI_API_KEY", "")
from auditor import Issue, audit, to_dataframe
from crawler import Crawler

# ── Page config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Content CT",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Styles ───────────────────────────────────────────────────────────────────

st.markdown("""
<style>
.block-container { padding-top: 1.5rem; }

.ct-title {
    font-size: 2rem;
    font-weight: 700;
    color: #0f3460;
    margin-bottom: 0;
}
.ct-sub {
    color: #6b7280;
    font-size: 0.9rem;
    margin-top: 0.2rem;
    margin-bottom: 1.5rem;
}

.metric-card {
    background: white;
    border-radius: 10px;
    padding: 0.9rem 1rem;
    border: 1px solid #e5e7eb;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    text-align: center;
}
.metric-label {
    font-size: 0.72rem;
    color: #6b7280;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}
.metric-value {
    font-size: 1.9rem;
    font-weight: 700;
    line-height: 1.15;
    margin-top: 0.15rem;
}
.c-blue    { color: #0f3460; }
.c-gray    { color: #374151; }
.c-red     { color: #dc2626; }
.c-orange  { color: #ea580c; }
.c-amber   { color: #d97706; }
.c-purple  { color: #7c3aed; }
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────────────────

_DEFAULTS = {
    "pages": [],
    "issues": [],
    "issues_df": pd.DataFrame(),
    "crawl_done": False,
    "pages_crawled": 0,
    "ai_calls_made": 0,
}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🔬 Content CT")
    st.caption("A CAT scan for your site's content problems")
    st.divider()

    st.subheader("Crawl Settings")
    url_input = st.text_input("Start URL", placeholder="https://example.com")
    max_pages = st.slider("Max pages", min_value=10, max_value=2500, value=100, step=10)
    delay = st.select_slider(
        "Crawl delay (s)",
        options=[0.0, 0.25, 0.5, 1.0, 2.0],
        value=0.5,
        help="Pause between requests. Increase for polite crawling of smaller sites.",
    )
    respect_robots = st.toggle("Respect robots.txt", value=True)
    exclude_paths_input = st.text_input(
        "Exclude Paths (comma-separated)",
        placeholder="/blog, /admin, /tag/",
        help="Skip crawling any paths that contain these strings."
    )
    include_paths_input = st.text_input(
        "Include ONLY Paths (comma-separated)",
        placeholder="/products, /category/",
        help="If set, only the Start URL and URLs containing these strings will be crawled."
    )

    st.divider()
    st.subheader("AI Fix Suggestions")
    ai_enabled = st.toggle("Enable AI suggestions", value=False)

    if ai_enabled:
        ai_provider = st.radio(
            "Provider",
            ["Claude (Anthropic)", "Gemini (Google)"],
            horizontal=True,
            help="Gemini Flash is cheaper for high-volume audits. Claude is stronger for copywriting.",
        )
        if ai_provider == "Gemini (Google)":
            if _ENV_GEMINI:
                st.success("Gemini API key loaded from environment ✓")
                api_key_input = _ENV_GEMINI
            else:
                api_key_input = st.text_input(
                    "Gemini API Key",
                    type="password",
                    placeholder="AIza...",
                    help="Get one at aistudio.google.com/apikey — free tier available",
                )
        else:
            if _ENV_ANTHROPIC:
                st.success("Anthropic API key loaded from environment ✓")
                api_key_input = _ENV_ANTHROPIC
            else:
                api_key_input = st.text_input(
                    "Anthropic API Key",
                    type="password",
                    placeholder="sk-ant-...",
                    help="Get one at console.anthropic.com",
                )
        max_ai_calls = st.slider(
            "Max AI calls",
            min_value=5,
            max_value=100,
            value=25,
            step=5,
            help="Caps API usage to control cost. Prioritises missing alt text, then meta descriptions.",
        )
        st.caption("Generate suggestions for:")
        ai_missing_alt = st.checkbox("Missing alt text", value=True)
        ai_empty_alt   = st.checkbox("Empty alt text",   value=True)
        ai_poor_alt    = st.checkbox("Poor / filename alt text", value=True)
        ai_meta        = st.checkbox("Missing meta descriptions", value=True)
        ai_title       = st.checkbox("Missing title tags", value=False)
    else:
        ai_provider = "Claude (Anthropic)"
        api_key_input = ""
        max_ai_calls = 25
        ai_missing_alt = ai_empty_alt = ai_poor_alt = ai_meta = ai_title = False

    st.divider()
    start_btn = st.button("▶  Start Audit", type="primary", use_container_width=True)

    if st.session_state.crawl_done:
        if st.button("↺  New Audit", use_container_width=True):
            for _k, _v in _DEFAULTS.items():
                st.session_state[_k] = _v
            st.rerun()

# ── Header ────────────────────────────────────────────────────────────────────

st.markdown('<div class="ct-title">🔬 Content CT</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="ct-sub">A CAT scan for your site\'s content problems — '
    "finds SEO issues, drafts fixes</div>",
    unsafe_allow_html=True,
)

# ── Run audit ─────────────────────────────────────────────────────────────────

if start_btn:
    if not url_input or not url_input.startswith("http"):
        st.error("Please enter a valid URL starting with http:// or https://")
        st.stop()
    if ai_enabled and not api_key_input:
        provider_name = "Gemini" if ai_provider == "Gemini (Google)" else "Anthropic"
        st.error(f"Enter your {provider_name} API key to use AI suggestions, or turn AI off.")
        st.stop()

    # Reset
    for _k, _v in _DEFAULTS.items():
        st.session_state[_k] = _v

    # ── Crawl ──────────────────────────────────────────────────────────────
    exclude_list = [p.strip() for p in exclude_paths_input.split(",") if p.strip()] if exclude_paths_input else []
    include_list = [p.strip() for p in include_paths_input.split(",") if p.strip()] if include_paths_input else []
    
    crawler = Crawler(
        url_input,
        max_pages=max_pages,
        delay=delay,
        respect_robots=respect_robots,
        exclude_paths=exclude_list,
        include_paths=include_list,
    )

    st.markdown("#### Crawling…")
    prog_bar   = st.progress(0.0)
    status_txt = st.empty()
    pages = []

    for page_data, done, in_queue in crawler.crawl():
        pages.append(page_data)
        total_est = max(done + in_queue, max_pages)
        prog_bar.progress(min(done / total_est, 1.0))
        status_txt.caption(f"Page {done} — {page_data.url[:90]}")

    prog_bar.empty()
    status_txt.empty()

    # ── Audit ──────────────────────────────────────────────────────────────
    with st.spinner("Analysing pages for SEO issues…"):
        issues = audit(pages)

    # ── AI enhancement ─────────────────────────────────────────────────────
    ai_calls = 0
    if ai_enabled and api_key_input and issues:
        provider_key = "Gemini" if ai_provider == "Gemini (Google)" else "Claude"
        advisor = create_advisor(provider_key, api_key_input)
        page_lookup = {p.url: p for p in pages}

        target_types = set()
        if ai_missing_alt: target_types.add("missing_alt")
        if ai_empty_alt:   target_types.add("empty_alt")
        if ai_poor_alt:    target_types.add("poor_alt")
        if ai_meta:        target_types.add("missing_meta")
        if ai_title:       target_types.add("missing_title")

        ai_candidates = []
        for i in issues:
            if i.issue_type in target_types:
                ai_candidates.append(i)
                if len(ai_candidates) == int(max_ai_calls):
                    break

        if ai_candidates:
            st.markdown("#### Generating AI suggestions…")
            ai_prog = st.progress(0.0)
            ai_stat = st.empty()

            successful_ai_calls = []

            for idx, issue in enumerate(ai_candidates):
                if len(successful_ai_calls) == int(max_ai_calls):
                    break

                page = page_lookup.get(issue.url)
                context = page.content_snippet if page else ""

                if issue.issue_type in ("missing_alt", "empty_alt", "poor_alt") and issue.image_src:
                    ai_stat.caption(
                        f"Alt text {len(successful_ai_calls) + 1}/{min(len(ai_candidates), int(max_ai_calls))} — "
                        f"{issue.image_src[:60]}"
                    )
                    draft = advisor.generate_alt_text(issue.image_src, context)
                    if draft and not draft.startswith("("):
                        issue.suggested_fix = f'Suggested alt text: "{draft}"'
                        issue.ai_suggested = True
                        successful_ai_calls.append(1)

                elif issue.issue_type == "missing_meta" and page:
                    ai_stat.caption(
                        f"Meta description {len(successful_ai_calls) + 1}/{min(len(ai_candidates), int(max_ai_calls))} — "
                        f"{issue.url[:60]}"
                    )
                    h1 = page.h1s[0] if page.h1s else ""
                    draft = advisor.draft_meta_description(
                        page.url, page.title, h1, context
                    )
                    if draft and not draft.startswith("("):
                        issue.suggested_fix = f'Suggested description: "{draft}"'
                        issue.ai_suggested = True
                        successful_ai_calls.append(1)

                elif issue.issue_type == "missing_title" and page:
                    ai_stat.caption(
                        f"Title tag {len(successful_ai_calls) + 1}/{min(len(ai_candidates), int(max_ai_calls))} — "
                        f"{issue.url[:60]}"
                    )
                    h1 = page.h1s[0] if page.h1s else ""
                    draft = advisor.draft_title(page.url, h1, context)
                    if draft and not draft.startswith("("):
                        issue.suggested_fix = f'Suggested title: "{draft}"'
                        issue.ai_suggested = True
                        successful_ai_calls.append(1)

                ai_prog.progress((idx + 1) / len(ai_candidates))

            ai_prog.empty()
            ai_stat.empty()
            
            ai_calls = len(successful_ai_calls)

    # Store results
    st.session_state.pages = pages
    st.session_state.issues = issues
    st.session_state.issues_df = to_dataframe(issues)
    st.session_state.pages_crawled = len(pages)
    st.session_state.ai_calls_made = ai_calls
    st.session_state.crawl_done = True
    st.rerun()

# ── Results ───────────────────────────────────────────────────────────────────

if st.session_state.crawl_done:
    issues   = st.session_state.issues
    df       = st.session_state.issues_df
    n_pages  = st.session_state.pages_crawled
    n_ai     = st.session_state.ai_calls_made

    n_crit   = sum(1 for i in issues if i.severity == "Critical")
    n_high   = sum(1 for i in issues if i.severity == "High")
    n_med    = sum(1 for i in issues if i.severity == "Medium")
    n_low    = sum(1 for i in issues if i.severity == "Low")

    def _card(label, value, colour_class):
        return (
            f'<div class="metric-card">'
            f'<div class="metric-label">{label}</div>'
            f'<div class="metric-value {colour_class}">{value}</div>'
            f"</div>"
        )

    cols = st.columns(7)
    cards = [
        ("Pages Crawled",   n_pages,          "c-blue"),
        ("Total Issues",    len(issues),       "c-gray"),
        ("Critical",        n_crit,            "c-red"),
        ("High",            n_high,            "c-orange"),
        ("Medium",          n_med,             "c-amber"),
        ("Low",             n_low,             "c-gray"),
        ("AI Fixes",        n_ai,              "c-purple"),
    ]
    for col, (label, val, cls) in zip(cols, cards):
        col.markdown(_card(label, val, cls), unsafe_allow_html=True)

    st.markdown("")

    # ── Filters ────────────────────────────────────────────────────────────
    fc1, fc2, fc3 = st.columns([2, 2, 3])
    with fc1:
        sev_filter = st.multiselect(
            "Severity",
            ["Critical", "High", "Medium", "Low"],
            default=["Critical", "High", "Medium", "Low"],
        )
    with fc2:
        type_options = sorted(df["Issue Type"].unique().tolist()) if not df.empty else []
        type_filter = st.multiselect("Issue Type", type_options)
    with fc3:
        url_search = st.text_input("Filter by URL", placeholder="e.g. /blog/")

    # Apply filters
    filtered = df.copy() if not df.empty else df
    if not filtered.empty:
        if sev_filter:
            filtered = filtered[filtered["Severity"].isin(sev_filter)]
        if type_filter:
            filtered = filtered[filtered["Issue Type"].isin(type_filter)]
        if url_search:
            filtered = filtered[
                filtered["URL"].str.contains(url_search, case=False, na=False)
            ]

    # ── Download + row count ────────────────────────────────────────────────
    dl_col, info_col = st.columns([2, 5])
    with dl_col:
        if not df.empty:
            st.download_button(
                "⬇  Download Full CSV",
                data=df.to_csv(index=False).encode("utf-8"),
                file_name="content_ct_audit.csv",
                mime="text/csv",
                use_container_width=True,
            )
    with info_col:
        st.caption(f"Showing **{len(filtered)}** of **{len(df)}** issues")
        if n_ai > 0:
            st.caption(f"✨ {n_ai} AI-generated suggestions included (marked with ✓ in the AI Generated column)")

    # ── Issues table ────────────────────────────────────────────────────────
    if not filtered.empty:
        st.dataframe(
            filtered,
            use_container_width=True,
            height=520,
            column_config={
                "URL": st.column_config.LinkColumn("URL", max_chars=65),
                "Page Title": st.column_config.TextColumn("Page Title", width="medium"),
                "Issue Type": st.column_config.TextColumn("Issue Type", width="medium"),
                "Severity": st.column_config.TextColumn("Severity", width="small"),
                "Suggested Fix": st.column_config.TextColumn("Suggested Fix", width="large"),
                "AI Generated": st.column_config.TextColumn("AI ✨", width="small"),
            },
            hide_index=True,
        )
    elif df.empty:
        st.success("No SEO issues found! 🎉")
    else:
        st.info("No issues match the current filters.")

    # ── Breakdown by issue type ─────────────────────────────────────────────
    if not df.empty:
        with st.expander("Issue breakdown by type"):
            breakdown = (
                df.groupby(["Issue Type", "Severity"])
                .size()
                .reset_index(name="Count")
                .sort_values("Count", ascending=False)
            )
            st.dataframe(breakdown, use_container_width=True, hide_index=True)

# ── Landing state ─────────────────────────────────────────────────────────────

elif not st.session_state.crawl_done:
    st.info("Enter a URL in the sidebar and click **▶ Start Audit** to begin.")

    with st.expander("What Content CT checks", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("""
**Metadata**
- Missing / duplicate title tags
- Title length (30–60 chars)
- Missing / duplicate meta descriptions
- Meta description length (70–160 chars)
""")
        with c2:
            st.markdown("""
**On-page structure**
- Missing or multiple H1 tags
- Missing, empty, or poor alt text
- Missing canonical tags
- Redirect chains
""")
        with c3:
            st.markdown("""
**Health & performance**
- Broken pages (4xx / 5xx)
- Thin content (<300 words)
- Slow page loads (>3s)

**With AI enabled**
- Auto-drafted alt text (vision)
- Auto-drafted meta descriptions
- Auto-drafted title tags
""")

    if ai_enabled:
        st.success(
            "✨ **AI suggestions enabled** — Claude will draft alt text, "
            "meta descriptions, and title tags for flagged issues."
        )
