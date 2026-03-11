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
# TAB 3: URL STRUCTURE MAPPER & STRATEGIST ENGINE
# ==========================================
with tab3:
    st.header("🗂️ URL Structure Mapper & Strategist Engine")
    st.markdown("Paste a list of URLs to instantly dissect their folder structure, identify deep silos, and catch formatting errors.")
    
    url_input = st.text_area("Paste URLs (One per line):", height=150, placeholder="https://www.columbiadoctors.org/specialties/cardiology\nhttps://www.columbiadoctors.org/specialties/neurology")
    
    if st.button("🗺️ Map Architecture & Generate Strategy", type="primary"):
        urls = [u.strip() for u in url_input.split('\n') if u.strip()]
        if not urls:
            st.error("Please paste at least one URL.")
        else:
            with st.spinner("Mapping URL architecture and running diagnostics..."):
                try:
                    url_df = adv.url_to_df(urls)
                    st.success(f"✅ Architecture Mapped for {len(urls)} URLs. Generating Strategic Report...")
                    
                    st.subheader("🧠 Automated Diagnostic Report")
                    
                    # Diagnostic 1: Site Depth & Siloing
                    with st.expander("🚨 Diagnostic 1: Architecture Depth & Siloing", expanded=True):
                        st.markdown("**Severity:** Medium | **Impact:** Crawlability & Link Equity Flow")
                        
                        # Top Silos
                        if 'dir_1' in url_df.columns:
                            top_silos = url_df['dir_1'].value_counts().head(5)
                            st.write("**Top Level Folders (Silos):**")
                            st.bar_chart(top_silos)
                            st.markdown("""
                            **Strategist Note:** Ensure these top folders align with your primary service lines. If a random or generic folder dominates, your internal link equity is being misdirected.
                            """)
                        
                        # Depth Check (Flag URLs that are 4+ folders deep)
                        deep_urls = pd.DataFrame()
                        if 'dir_4' in url_df.columns: 
                            deep_urls = url_df[url_df['dir_4'].notna() & (url_df['dir_4'] != '')]
                        
                        if not deep_urls.empty:
                            st.warning(f"**Found {len(deep_urls)} URLs buried 4+ directories deep.**")
                            st.markdown("""
                            **Strategist Action Plan (For IA / Content Team):**
                            A flat architecture is better for SEO. Pages buried 4+ clicks deep are rarely crawled by Google and receive very little 'link equity'. Consider flattening these URLs or linking to them directly from the homepage/primary hub.
                            """)
                            st.dataframe(deep_urls[['url']].head(5), use_container_width=True)
                        else:
                            st.success("✅ Architecture depth looks good. Pages are not buried too deeply.")

                    # Diagnostic 2: URL Formatting & Best Practices
                    with st.expander("🚨 Diagnostic 2: URL Formatting & Parameter Risks", expanded=True):
                        st.markdown("**Severity:** Medium | **Impact:** Duplicate Content & UX")
                        
                        issues_found = False
                        
                        # Check for Uppercase Letters
                        uppercase_urls = url_df[url_df['url'].str.contains(r'[A-Z]', regex=True, na=False)]
                        if not uppercase_urls.empty:
                            issues_found = True
                            st.warning(f"**Found {len(uppercase_urls)} URLs containing uppercase letters.**")
                            st.markdown("*(Rule: URLs should always be 100% lowercase to prevent Linux servers from creating duplicate pages like `/Cardiology` vs `/cardiology`.)*")
                        
                        # Check for Underscores
                        underscore_urls = url_df[url_df['url'].str.contains(r'_', regex=True, na=False)]
                        if not underscore_urls.empty:
                            issues_found = True
                            st.warning(f"**Found {len(underscore_urls)} URLs using underscores instead of hyphens.**")
                            st.markdown("*(Rule: Google reads hyphens (`-`) as word separators, but it joins words connected by underscores (`_`). Use hyphens for all multi-word URLs.)*")
                            
                        # Check for Query Parameters
                        if 'query' in url_df.columns:
                            param_urls = url_df[url_df['query'].notna() & (url_df['query'] != '')]
                            if not param_urls.empty:
                                issues_found = True
                                st.warning(f"**Found {len(param_urls)} URLs with dynamic query parameters (e.g., `?id=123`).**")
                                st.markdown("*(Rule: Dynamic parameters can cause massive index bloat if Google crawls every variation. Ensure Canonical tags are in place.)*")
                                
                        if not issues_found:
                            st.success("✅ All URLs follow strict formatting best practices (lowercase, hyphens, static paths).")

                    # Raw Data Drop
                    st.markdown("---")
                    st.subheader("Raw URL Database")
                    st.dataframe(url_df, use_container_width=True)
                    
                except Exception as e:
                    st.error(f"Failed to map URLs. Error: {e}")

# ==========================================
# TAB 4: N-GRAM & CANNIBALIZATION ANALYZER
# ==========================================
with tab4:
    st.header("🧠 N-Gram & Keyword Cannibalization Analyzer")
    st.markdown("Analyze meta titles and H1s to identify keyword cannibalization, and export the exact URLs causing the conflict.")
    
    # --- Persistent Exclusions Logic ---
    EXCLUSIONS_FILE = "exclusions.txt"
    DEFAULT_EXCLUSIONS = "columbiadoctors, cuimc, columbia university, vagelos, college of physicians, mailman, school of nursing, college of dental medicine, irving medical center, department of, division of"
    
    # Load exclusions from file, or create it if missing
    if not os.path.exists(EXCLUSIONS_FILE):
        with open(EXCLUSIONS_FILE, "w") as f:
            f.write(DEFAULT_EXCLUSIONS)
            
    with open(EXCLUSIONS_FILE, "r") as f:
        current_exclusions = f.read().strip()

    uploaded_file = st.file_uploader("Upload Crawl Data (CSV)", type=["csv"])
    
    if uploaded_file:
        df_text = pd.read_csv(uploaded_file, low_memory=False)
        st.success(f"✅ Loaded dataset with {len(df_text)} rows.")
        
        # --- UI Settings ---
        col1, col2 = st.columns([1, 1])
        with col1:
            text_cols = [c for c in df_text.columns if 'Title' in c or 'H1' in c or 'H2' in c or 'Description' in c]
            if not text_cols: text_cols = df_text.columns.tolist()
            text_col = st.selectbox("Select SEO Element to Analyze:", text_cols)
            
            url_cols = [c for c in df_text.columns if c.lower() in ['address', 'url', 'loc', 'link']]
            if not url_cols: url_cols = df_text.columns.tolist()
            url_col = st.selectbox("Select URL/Address Column for Mapping:", url_cols)
            
            n_gram_size = st.slider("Phrase Length (Words):", 2, 5, 3)
            
        with col2:
            st.markdown("**Brand Boilerplate Exclusion Database**")
            updated_exclusions = st.text_area(
                "Edit and save your custom exclusion list (comma separated):", 
                value=current_exclusions,
                height=130
            )
            
            # Save Button for the Database
            if st.button("💾 Save to Exclusion Database"):
                with open(EXCLUSIONS_FILE, "w") as f:
                    f.write(updated_exclusions)
                st.success("✅ Exclusions saved and applied for this session!")

        if st.button("🔍 Analyze and Map URLs", type="primary"):
            with st.spinner("Analyzing semantics and mapping phrases to URLs..."):
                try:
                    df_text['__clean_text'] = df_text[text_col].astype(str).str.lower()
                    
                    # Read the most freshly saved exclusions
                    with open(EXCLUSIONS_FILE, "r") as f:
                        active_exclusions = f.read().strip()
                        
                    exclusions = [e.strip().lower() for e in active_exclusions.split(',') if e.strip()]
                    
                    cleaned_texts = []
                    for text in df_text['__clean_text']:
                        for exc in exclusions:
                            text = text.replace(exc, ' ')
                        cleaned_texts.append(text)
                        
                    word_freq = adv.word_frequency(cleaned_texts, phrase_len=n_gram_size)
                    
                    st.subheader("🧠 Cannibalization Diagnostic & Export")
                    
                    if 'abs_freq' in word_freq.columns:
                        cannibalized = word_freq[word_freq['abs_freq'] > 3].head(20)
                        
                        if not cannibalized.empty:
                            st.warning(f"**Found {len(cannibalized)} phrases competing across multiple pages.**")
                            
                            mapping_data = []
                            for phrase in cannibalized['word']:
                                matching_rows = df_text[df_text['__clean_text'].str.contains(phrase, regex=False, na=False)]
                                for _, row in matching_rows.iterrows():
                                    mapping_data.append({
                                        'Cannibalized Phrase': phrase,
                                        'Original Text Element': row[text_col],
                                        'URL': row[url_col]
                                    })
                                    
                            mapping_df = pd.DataFrame(mapping_data)
                            st.dataframe(mapping_df, use_container_width=True)
                            
                            csv = mapping_df.to_csv(index=False).encode('utf-8')
                            st.download_button(
                                label="📥 Download URL Mapping Report (CSV)",
                                data=csv,
                                file_name="cannibalization_url_mapping.csv",
                                mime="text/csv",
                                type="primary"
                            )
                        else:
                            st.success("✅ No major cannibalization detected! Topics look well-siloed.")
                    else:
                        st.info("Not enough data to find repeated phrases.")

                    df_text.drop(columns=['__clean_text'], inplace=True)
                    
                except Exception as e:
                    st.error(f"Analysis Failed. Error: {e}")
