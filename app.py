import streamlit as st
import advertools as adv
import pandas as pd
import datetime
from urllib.parse import urlparse
import os

# 1. Page Configuration & UI Setup
st.set_page_config(page_title="Healthcare SEO Auditor", page_icon="🏥", layout="wide")

st.title("🏥 Healthcare SEO Strategist Dashboard")
st.markdown("""
**Objective:** Audit medical websites for **E-E-A-T signals**, thin content, and strict meta description frameworks.
* **Meta Descriptions:** Enforcing the *Empathy + Authority + Action* framework (140-150 chars).
* **Thin Content:** Flagging pages < 300 words that require physician quotes or medical review citations.
""")

st.divider()

# 2. Sidebar Inputs
with st.sidebar:
    st.header("Crawl Parameters")
    target_url = st.text_input("Target URL:", value="columbianephrology.org")
    max_urls = st.number_input("Max URLs to crawl (0 = unlimited):", min_value=0, value=50, step=10)
    run_audit = st.button("🚀 Run SEO Audit", type="primary")

# 3. Execution Logic
if run_audit:
    # Ensure URL is properly formatted
    if not target_url.startswith("http://") and not target_url.startswith("https://"):
        target_url = "https://" + target_url

    domain = urlparse(target_url).netloc.replace("www.", "")
    output_file = f"{domain}_crawl.jl"

    # Remove previous crawl file if it exists to prevent appending old data
    if os.path.exists(output_file):
        os.remove(output_file)

    custom_settings = {
        'CONCURRENT_REQUESTS_PER_DOMAIN': 2,
        'LOG_LEVEL': 'WARNING'
    }
    
    if max_urls > 0:
        custom_settings['CLOSESPIDER_PAGECOUNT'] = max_urls

    with st.spinner(f"Crawling {domain}... Please wait, this takes a moment."):
        try:
            # Run the advertools crawler
            adv.crawl(target_url, output_file, follow_links=True, allowed_domains=[domain], custom_settings=custom_settings)
            
            # Load and clean data
            df = pd.read_json(output_file, lines=True)
            
            # Filter for 200 OK HTML pages
            df_html = df.copy()
            if 'status' in df_html.columns:
                df_html = df_html[df_html['status'] == 200]
            if 'resp_headers_content-type' in df_html.columns:
                df_html = df_html[df_html['resp_headers_content-type'].str.contains('text/html', na=False, case=False)]

            # A. Thin Content Audit
            if 'body_text' in df_html.columns:
                df_html['word_count'] = df_html['body_text'].fillna('').apply(lambda x: len(str(x).split()))
                df_html['thin_content_flag'] = df_html['word_count'].apply(lambda x: '🚨 Yes (<300 words)' if x < 300 else '✅ No')
            else:
                df_html['word_count'] = 0
                df_html['thin_content_flag'] = "Unknown"

            # B. Meta Description Length Audit
            if 'meta_desc' in df_html.columns:
                df_html['meta_desc_clean'] = df_html['meta_desc'].apply(lambda x: x[0] if isinstance(x, list) else str(x))
                df_html['meta_desc_length'] = df_html['meta_desc_clean'].str.len()

                def check_meta_length(length):
                    if pd.isna(length) or length == 0:
                        return "❌ Missing"
                    elif length < 140:
                        return "⚠️ Too Short (<140)"
                    elif length > 150:
                        return "⚠️ Too Long (>150)"
                    else:
                        return "✅ Optimized (140-150)"

                df_html['meta_desc_status'] = df_html['meta_desc_length'].apply(check_meta_length)
            else:
                df_html['meta_desc_clean'] = "None Found"
                df_html['meta_desc_length'] = 0
                df_html['meta_desc_status'] = "❌ Missing"

            # Clean output for the dashboard
            export_cols = ['url', 'title', 'meta_desc_clean', 'meta_desc_length', 'meta_desc_status', 'word_count', 'thin_content_flag']
            export_cols = [col for col in export_cols if col in df_html.columns]
            final_df = df_html[export_cols]

            # 4. Display Results in UI
            st.success(f"Audit Complete! Processed {len(final_df)} pages.")
            
            # Show Metrics
            col1, col2, col3 = st.columns(3)
            col1.metric("Pages Audited", len(final_df))
            col2.metric("Thin Content Issues", len(final_df[final_df['thin_content_flag'].str.contains('Yes')]))
            col3.metric("Meta Desc Issues", len(final_df[~final_df['meta_desc_status'].str.contains('✅')]))

            st.dataframe(final_df, use_container_width=True)

            # 5. Provide CSV Download
            csv = final_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Strategic Audit (CSV)",
                data=csv,
                file_name=f"{domain}_SEO_Audit_{datetime.datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                type="primary"
            )

        except Exception as e:
            st.error(f"Crawl Failed. Ensure the URL is accessible. Error detail: {e}")
