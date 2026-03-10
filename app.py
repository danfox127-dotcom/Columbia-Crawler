import streamlit as st
import advertools as adv
import pandas as pd
import datetime
import re
import requests
from urllib.parse import urlparse
import os
from collections import Counter

# --- Page Configuration ---
st.set_page_config(page_title="Healthcare SEO Command Center", page_icon="🏥", layout="wide")
st.title("🏥 Healthcare SEO Strategist Command Center")
st.markdown("An enterprise-grade, multi-tool dashboard for large-scale medical Information Architecture and E-E-A-T analysis.")

# --- Tab Setup ---
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🕷️ Live Crawler", 
    "🗺️ Sitemap Auditor", 
    "🗂️ URL Structure Mapper", 
    "🧠 N-Gram Analyzer",
    "🔗 Link Up Protocol"
])

# ==========================================
# TAB 1: LIVE CRAWLER (Screaming Frog Alternative)
# ==========================================
with tab1:
    st.header("🕷️ Live SEO Crawler & E-E-A-T Auditor")
    st.markdown("Crawl a live site to grade Meta Descriptions (140-150 chars) and flag Thin Content (<300 words).")
    
    colA, colB = st.columns([1, 2])
    with colA:
        target_url = st.text_input("Target Domain:", value="https://www.columbianephrology.org")
        max_urls = st.number_input("Max URLs to crawl (0 = unlimited):", min_value=0, value=50, step=10)
        run_audit = st.button("🚀 Run Live Crawl", type="primary")

if run_audit:
        # 1. Ensure the URL has a protocol
        if not target_url.startswith("http"): 
            target_url = "https://" + target_url
            
        # 2. Extract domain and strictly strip "www." to prevent Scrapy from blocking redirects
        domain = urlparse(target_url).netloc.replace("www.", "")
        
        output_file = f"{domain}_crawl.jl"

        if os.path.exists(output_file): 
            os.remove(output_file)

        custom_settings = {'CONCURRENT_REQUESTS_PER_DOMAIN': 2, 'LOG_LEVEL': 'WARNING'}
        if max_urls > 0: custom_settings['CLOSESPIDER_PAGECOUNT'] = max_urls

        with st.spinner(f"Crawling {domain}... Please wait."):
            try:
                adv.crawl(target_url, output_file, follow_links=True, allowed_domains=[domain], custom_settings=custom_settings)
                df = pd.read_json(output_file, lines=True)
                
                df_html = df[df.get('status', pd.Series([200]*len(df))) == 200].copy()
                
                if 'body_text' in df_html.columns:
                    df_html['word_count'] = df_html['body_text'].fillna('').apply(lambda x: len(str(x).split()))
                    df_html['thin_content_flag'] = df_html['word_count'].apply(lambda x: '🚨 Yes (<300 words)' if x < 300 else '✅ No')
                
                if 'meta_desc' in df_html.columns:
                    df_html['meta_desc_clean'] = df_html['meta_desc'].apply(lambda x: x[0] if isinstance(x, list) else str(x))
                    df_html['meta_desc_length'] = df_html['meta_desc_clean'].str.len()
                    df_html['meta_desc_status'] = df_html['meta_desc_length'].apply(
                        lambda l: "❌ Missing" if pd.isna(l) or l==0 else ("⚠️ Too Short" if l<140 else ("⚠️ Too Long" if l>150 else "✅ Optimized"))
                    )

                export_cols = ['url', 'title', 'meta_desc_clean', 'meta_desc_length', 'meta_desc_status', 'word_count', 'thin_content_flag']
                final_df = df_html[[c for c in export_cols if c in df_html.columns]]

                st.success(f"Audit Complete! Processed {len(final_df)} pages.")
                st.dataframe(final_df, use_container_width=True)
                st.download_button("📥 Download Audit (CSV)", data=final_df.to_csv(index=False).encode('utf-8'), file_name=f"{domain}_SEO_Audit.csv", mime="text/csv")
            except Exception as e:
                st.error(f"Crawl Failed: {e}")

# ==========================================
# TAB 2: SITEMAP AUDITOR
# ==========================================
with tab2:
    st.header("🗺️ XML Sitemap Auditor")
    st.markdown("Instantly parse massive sitemaps to check indexability signals and structure.")
    
    sitemap_url = st.text_input("XML Sitemap URL:", placeholder="https://www.columbiadoctors.org/sitemap.xml")
    run_sitemap = st.button("📊 Analyze Sitemap", type="primary")
    
    if run_sitemap and sitemap_url:
        with st.spinner("Downloading and parsing sitemap network..."):
            try:
                sitemap_df = adv.sitemap_to_df(sitemap_url)
                st.success(f"Successfully extracted {len(sitemap_df)} URLs.")
                
                col1, col2 = st.columns(2)
                col1.metric("Total URLs Found", len(sitemap_df))
                if 'lastmod' in sitemap_df.columns:
                    missing_dates = sitemap_df['lastmod'].isna().sum()
                    col2.metric("Missing LastMod Dates", missing_dates, delta="Flag for SEO Fix" if missing_dates > 0 else "Optimized", delta_color="inverse")
                
                st.dataframe(sitemap_df.head(100), use_container_width=True)
                st.download_button("📥 Download Sitemap Data", data=sitemap_df.to_csv(index=False).encode('utf-8'), file_name="sitemap_audit.csv", mime="text/csv")
            except Exception as e:
                st.error(f"Failed to parse sitemap. Ensure it is a valid XML URL. Error: {e}")

# ==========================================
# TAB 3: URL STRUCTURE MAPPER
# ==========================================
with tab3:
    st.header("🗂️ URL Structure & Silo Mapper")
    st.markdown("Paste a list of URLs to instantly dissect their folder structure and hierarchy.")
    
    url_input = st.text_area("Paste URLs (One per line):", height=150)
    run_urls = st.button("🗺️ Map Architecture", type="primary")
    
    if run_urls and url_input:
        urls = [u.strip() for u in url_input.split('\n') if u.strip()]
        with st.spinner("Mapping URL architecture..."):
            url_df = adv.url_to_df(urls)
            st.success("Architecture Mapped!")
            
            # Show directory breakdown if available
            dir_cols = [c for c in url_df.columns if c.startswith('dir_')]
            if dir_cols:
                st.subheader("Top Level Directories (Silos)")
                st.bar_chart(url_df['dir_1'].value_counts().head(10))
            
            st.dataframe(url_df, use_container_width=True)

# ==========================================
# TAB 4: N-GRAM & CANNIBALIZATION ANALYZER
# ==========================================
with tab4:
    st.header("🧠 N-Gram & Keyword Cannibalization Analyzer")
    st.markdown("Upload a crawl CSV (like Screaming Frog) to find overused phrases in H1s or Titles.")
    
    uploaded_file = st.file_uploader("Upload CSV Dump", type=["csv"])
    if uploaded_file:
        df_text = pd.read_csv(uploaded_file, low_memory=False)
        st.write(f"Loaded {len(df_text)} rows.")
        
        text_col = st.selectbox("Select Column to Analyze (e.g., Title 1, H1-1):", df_text.columns)
        n_gram_size = st.slider("Phrase Length (Words):", 1, 4, 2)
        run_ngram = st.button("🔍 Extract Phrases", type="primary")
        
        if run_ngram:
            with st.spinner("Analyzing semantic patterns..."):
                text_data = df_text[text_col].dropna().astype(str).tolist()
                
                # Simple N-Gram extraction using advertools word_frequency
                word_freq = adv.word_frequency(text_data, phrase_len=n_gram_size)
                
                st.success("Analysis Complete. Watch out for overlapping concepts below.")
                st.dataframe(word_freq.head(50), use_container_width=True)

# ==========================================
# TAB 5: CONTEXTUAL AUTO-LINKER
# ==========================================
with tab5:
    st.header("🔗 Contextual Auto-Linker")
    st.markdown("Paste your copy below. The tool will scan your text against the Vagelos Database to find and validate internal linking opportunities.")

    draft_text = st.text_area("Paste Draft Copy Here:", height=250)
    
    col1, col2 = st.columns(2)
    with col1:
        manual_keyword = st.text_input("Manual Keyword Override (Optional):")
    with col2:
        manual_url = st.text_input("Manual URL Override (Optional):")

    if st.button("🚀 Scan and Link Content", type="primary"):
        if not draft_text:
            st.error("Please paste some text to scan.")
        else:
            with st.spinner("Scanning database for matches and validating live status..."):
                try:
                    # 1. Load Database
                    ref_df = pd.read_csv('Vagelos CSV.csv', low_memory=False)
                    # Filter out ESI noise and non-indexable junk
                    ref_df = ref_df[~ref_df['Address'].str.contains('/esi/', na=False)]
                    ref_df = ref_df[ref_df['Status Code'].astype(str) == '200']
                    
                    # 2. Identify Entities to Link
                    # We look for H1s from the CSV that exist inside your draft text
                    potential_matches = []
                    
                    # Search logic: Find H1s/Titles from the CSV that are present in the text
                    # We prioritize longer strings first to avoid partial matches
                    site_entities = ref_df[['Address', 'H1-1']].dropna()
                    site_entities = site_entities[site_entities['H1-1'].str.len() > 3]
                    
                    found_links = []
                    processed_text = draft_text

                    for _, row in site_entities.iterrows():
                        entity = row['H1-1'].strip()
                        url = row['Address']
                        
                        # Use regex for exact phrase match
                        pattern = r'(?i)\b({})\b'.format(re.escape(entity))
                        
                        if re.search(pattern, processed_text):
                            # Verify if it's still live
                            try:
                                res = requests.head(url, timeout=3)
                                if res.status_code == 200:
                                    # Apply the link to the first instance
                                    processed_text = re.sub(pattern, f'<a href="{url}">\g<1></a>', processed_text, count=1)
                                    found_links.append(f"Linked: **{entity}** to {url}")
                            except:
                                continue

                    # 3. Handle Manual Overrides if provided
                    if manual_keyword and manual_url:
                        pattern = r'(?i)\b({})\b'.format(re.escape(manual_keyword))
                        processed_text = re.sub(pattern, f'<a href="{manual_url}">\g<1></a>', processed_text, count=1)
                        found_links.append(f"Manual Link: **{manual_keyword}** applied.")

                    # 4. Results
                    st.success(f"Scan complete. Applied {len(found_links)} internal links.")
                    for link in found_links:
                        st.write(link)
                    
                    st.markdown("### Final HTML Output")
                    st.code(processed_text, language="html")
                    
                    st.markdown("### Preview")
                    st.markdown(processed_text, unsafe_allow_html=True)
                    
                except FileNotFoundError:
                    st.error("Missing 'Vagelos CSV.csv' in GitHub repo.")
                except Exception as e:
                    st.error(f"Analysis Error: {e}")
