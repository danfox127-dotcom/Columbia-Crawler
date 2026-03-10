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
with tab2:
    st.header("🗺️ XML Sitemap Auditor")
    sitemap_url = st.text_input("Sitemap URL:", placeholder="https://www.columbiadoctors.org/sitemap.xml")
    if st.button("📊 Analyze"):
        try:
            sitemap_df = adv.sitemap_to_df(sitemap_url)
            st.write(f"Found {len(sitemap_df)} URLs.")
            st.dataframe(sitemap_df)
        except Exception as e:
            st.error(f"Error: {e}")

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
