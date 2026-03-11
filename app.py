import streamlit as st
import advertools as adv
import pandas as pd
import re
import requests
from urllib.parse import urlparse
import os

# --- Page Configuration ---
st.set_page_config(page_title="Healthcare SEO Command Center", page_icon="🏥", layout="wide")
st.title("🏥 Healthcare SEO Strategist Command Center")

# --- Tab Setup (Streamlined) ---
tab1, tab2, tab3, tab4 = st.tabs([
    "🕷️ Live Crawler", 
    "🗺️ Sitemap Auditor", 
    "🗂️ URL Structure Mapper", 
    "🧠 N-Gram Analyzer"
])

# ==========================================
# TAB 1: LIVE CRAWLER
# ==========================================
with tab1:
    st.header("🕷️ Live SEO Crawler & E-E-A-T Auditor")
    colA, colB = st.columns([1, 2])
    with colA:
        target_url = st.text_input("Target Domain:", value="https://www.columbianephrology.org")
        max_urls = st.number_input("Max URLs:", min_value=0, value=50)
        run_audit = st.button("🚀 Run Live Crawl", type="primary")

    if run_audit:
        if not target_url.startswith("http"): target_url = "https://" + target_url
        domain = urlparse(target_url).netloc.replace("www.", "")
        output_file = f"{domain}_crawl.jl"
        if os.path.exists(output_file): os.remove(output_file)
        
        with st.spinner(f"Crawling {domain}..."):
            try:
                adv.crawl(target_url, output_file, follow_links=True, allowed_domains=[domain], 
                          custom_settings={'CLOSESPIDER_PAGECOUNT': max_urls if max_urls > 0 else None, 'LOG_LEVEL': 'WARNING'})
                df = pd.read_json(output_file, lines=True)
                df_html = df[df.get('status', pd.Series([200]*len(df))) == 200].copy()
                
                if 'body_text' in df_html.columns:
                    df_html['word_count'] = df_html['body_text'].fillna('').apply(lambda x: len(str(x).split()))
                
                st.dataframe(df_html[['url', 'title', 'word_count']] if 'word_count' in df_html.columns else df_html[['url', 'title']])
            except Exception as e:
                st.error(f"Error: {e}")

# ==========================================
# TAB 2: SITEMAP AUDITOR
# ==========================================
# ==========================================
# TAB 2: SITEMAP AUDITOR & STRATEGIST ENGINE
# ==========================================
with tab2:
    st.header("🗺️ XML Sitemap Auditor & Strategist Engine")
    st.markdown("Parse sitemaps and automatically generate actionable Information Architecture insights.")
    
    sitemap_url = st.text_input("Sitemap URL:", placeholder="https://www.columbiadoctors.org/sitemap.xml")
    
    if st.button("📊 Analyze & Generate Strategy", type="primary"):
        with st.spinner("Downloading sitemap and running Strategist diagnostics..."):
            try:
                sitemap_df = adv.sitemap_to_df(sitemap_url)
                st.success(f"✅ Extracted {len(sitemap_df)} URLs. Generating Strategic Report...")
                
                # --- STRATEGIST DIAGNOSTIC ENGINE ---
                st.subheader("🧠 Automated Diagnostic Report")
                
                # Diagnostic 1: E-E-A-T Freshness Audit
                if 'lastmod' in sitemap_df.columns:
                    sitemap_df['lastmod_dt'] = pd.to_datetime(sitemap_df['lastmod'], errors='coerce', utc=True)
                    now = pd.to_datetime('today', utc=True)
                    sitemap_df['age_days'] = (now - sitemap_df['lastmod_dt']).dt.days
                    
                    stale_1yr = sitemap_df[sitemap_df['age_days'] > 365]
                    stale_2yr = sitemap_df[sitemap_df['age_days'] > 730]
                    missing_date = sitemap_df[sitemap_df['lastmod'].isna()]
                    
                    with st.expander("🚨 Diagnostic 1: E-E-A-T Freshness Decay", expanded=True):
                        st.markdown(f"**Severity:** High | **Impact:** Loss of Medical Search Rankings")
                        st.markdown(f"- **{len(stale_2yr)} pages** haven't been updated in over 2 years.\n- **{len(stale_1yr)} pages** haven't been updated in over 1 year.")
                        st.markdown("""
                        **Strategist Action Plan (For Clinical Writers):** Google's YMYL (Your Money or Your Life) algorithm heavily demotes outdated medical content. 
                        1. Export this list.
                        2. Identify core condition/treatment pages that are over 2 years old.
                        3. Review clinical accuracy, update statistics, and republish in the CMS to refresh the `lastmod` timestamp.
                        """)
                        if not stale_2yr.empty:
                            st.write("**Highest Priority (Oldest Pages):**")
                            st.dataframe(stale_2yr[['loc', 'lastmod']].sort_values(by='lastmod').head(10), use_container_width=True)
                else:
                    st.warning("⚠️ No 'lastmod' dates found. This is a critical missed E-E-A-T signal for Googlebot.")

                # Diagnostic 2: CMS Index Bloat (Node/ESI Leaks)
                if 'loc' in sitemap_df.columns:
                    # Look for classic CMS garbage patterns
                    suspicious_urls = sitemap_df[sitemap_df['loc'].str.contains(r'/node/|/esi/|/tag/|/author/', na=False, regex=True)]
                    
                    with st.expander("🚨 Diagnostic 2: CMS Leaks & Index Bloat", expanded=True):
                        if not suspicious_urls.empty:
                            st.markdown(f"**Severity:** Critical | **Impact:** Crawl Budget Waste & Keyword Cannibalization")
                            st.markdown(f"**Found {len(suspicious_urls)} suspicious URLs** (e.g., raw `/node/` or `/esi/` fragments) leaking into the sitemap.")
                            st.markdown("""
                            **Strategist Action Plan (For Dev Team):**
                            These are un-aliased backend fragments. Hand this list to your backend developer and instruct them to update the `sitemap.xml` generation rules to strictly exclude raw nodes and cache fragments.
                            """)
                            st.dataframe(suspicious_urls[['loc']].head(10), use_container_width=True)
                        else:
                            st.success("✅ Architecture looks clean! No obvious `/node/` or `/esi/` CMS leaks detected in the sitemap.")

                # Raw Data Access
                st.markdown("---")
                st.subheader("Raw Sitemap Database")
                st.dataframe(sitemap_df, use_container_width=True)
                st.download_button("📥 Download Full CSV", data=sitemap_df.to_csv(index=False).encode('utf-8'), file_name="sitemap_audit.csv", mime="text/csv")

            except Exception as e:
                st.error(f"Failed to analyze sitemap. Error: {e}")

# ==========================================
# TAB 3: URL STRUCTURE MAPPER
# ==========================================
with tab3:
    st.header("🗂️ URL Structure Mapper")
    url_input = st.text_area("Paste URLs:")
    if st.button("🗺️ Map"):
        urls = [u.strip() for u in url_input.split('\n') if u.strip()]
        url_df = adv.url_to_df(urls)
        st.dataframe(url_df)

# ==========================================
# TAB 4: N-GRAM ANALYZER
# ==========================================
with tab4:
    st.header("🧠 N-Gram Analyzer")
    uploaded_file = st.file_uploader("Upload CSV", type=["csv"])
    if uploaded_file:
        df_text = pd.read_csv(uploaded_file, low_memory=False)
        text_col = st.selectbox("Column:", df_text.columns)
        n_gram_size = st.slider("Words:", 1, 4, 2)
        if st.button("🔍 Extract"):
            text_data = df_text[text_col].dropna().astype(str).tolist()
            word_freq = adv.word_frequency(text_data, phrase_len=n_gram_size)
            st.dataframe(word_freq)
