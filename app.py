import streamlit as st
import pandas as pd
import os
import io
import sys
import subprocess
from urllib.parse import urlparse
from scrapy.linkextractors import IGNORED_EXTENSIONS

# --- 1. PAGE CONFIG ---
st.set_page_config(page_title="Healthcare SEO Crawler", page_icon="🕷️", layout="wide")

# --- 2. SESSION STATE (keeps data alive across re-runs) ---
if "crawl_df" not in st.session_state:
    st.session_state.crawl_df = None
if "crawl_source" not in st.session_state:
    st.session_state.crawl_source = None  # "crawled" or "uploaded"

# --- 3. BANNED EXTENSIONS ---
banned_extensions = IGNORED_EXTENSIONS + ['gz', 'txt', 'zip', 'csv', 'pdf', 'docx', 'xlsx', 'tar']

# --- 4. SCRAPY SPIDER SCRIPT GENERATOR ---
def create_spider_script(start_url, max_pages, output_file):
    """Writes a temporary Scrapy spider script that crawls the given URL."""
    domain = urlparse(start_url).netloc

    page_limit_code = ""
    if max_pages and str(max_pages).lower() != "none" and int(max_pages) > 0:
        page_limit_code = f"'CLOSESPIDER_PAGECOUNT': {int(max_pages)},"

    script_content = f"""
import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.spiders import CrawlSpider, Rule
from scrapy.linkextractors import LinkExtractor

class SEOSitemapSpider(CrawlSpider):
    name = 'seo_spider'
    allowed_domains = ['{domain}']
    start_urls = ['{start_url}']

    rules = (
        Rule(
            LinkExtractor(deny_extensions={banned_extensions}),
            callback='parse_item',
            follow=True
        ),
    )

    custom_settings = {{
        'USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'ROBOTSTXT_OBEY': False,
        'DOWNLOAD_MAXSIZE': 5242880,
        'LOG_LEVEL': 'INFO',
        {page_limit_code}
        'FEEDS': {{
            '{output_file}': {{'format': 'jsonlines', 'overwrite': True}}
        }}
    }}

    def parse_item(self, response):
        yield {{
            'url': response.url,
            'status': response.status,
            'title': response.css('title::text').get(default='').strip(),
            'h1': response.css('h1::text').get(default='').strip(),
            'meta_desc': response.xpath("//meta[@name='description']/@content").get(default='').strip(),
            'word_count': len(response.xpath('//body//text()').getall())
        }}

if __name__ == "__main__":
    process = CrawlerProcess()
    process.crawl(SEOSitemapSpider)
    process.start()
"""
    with open("spider_script.py", "w", encoding="utf-8") as f:
        f.write(script_content)

# ============================================================
# SIDEBAR — Choose how to load data
# ============================================================
with st.sidebar:
    st.header("📂 Get Started")
    st.markdown(
        "Pick **one** of the options below to load SEO data. "
        "Your data stays in memory until you reload the page."
    )

    mode = st.radio(
        "How do you want to load data?",
        ["🕷️ Crawl a website", "📤 Upload a CSV"],
        help="Crawl scrapes a live site. Upload lets you re-use a previously downloaded CSV.",
    )

    st.divider()

    if mode == "🕷️ Crawl a website":
        st.subheader("⚙️ Crawler Settings")
        st.caption("Enter the starting URL and how many pages to crawl. The crawler follows internal links automatically.")
        target_url = st.text_input("Start URL", value="https://www.columbiamedicine.org/")
        max_pages_input = st.number_input(
            "Max Pages (0 = unlimited)",
            min_value=0, value=50, step=10,
            help="Set a limit so the crawl finishes faster. 0 means no limit.",
        )
        start_button = st.button("🚀 Start Crawl", type="primary", use_container_width=True)
    else:
        st.subheader("📤 Upload Previous Crawl")
        st.caption(
            "Upload a CSV that was previously downloaded from this tool "
            "(or any CSV with columns like **url**, **title**, **h1**, **meta_desc**)."
        )
        uploaded_file = st.file_uploader("Choose a CSV file", type="csv")
        start_button = False  # disable crawl button in upload mode

    # --- Clear data button ---
    if st.session_state.crawl_df is not None:
        st.divider()
        if st.button("🗑️ Clear loaded data", use_container_width=True):
            st.session_state.crawl_df = None
            st.session_state.crawl_source = None
            st.rerun()

# ============================================================
# MAIN AREA
# ============================================================
st.title("🕷️ Healthcare SEO Crawler")
st.markdown(
    "Crawl a healthcare website **or** upload a previous crawl CSV to instantly view "
    "page titles, H1s, meta descriptions, and status codes — all in one place."
)

output_jsonl = "crawl_output.jsonl"

# --- Handle CSV Upload ---
if mode == "📤 Upload a CSV" and uploaded_file is not None:
    try:
        df = pd.read_csv(uploaded_file)
        st.session_state.crawl_df = df
        st.session_state.crawl_source = "uploaded"
        st.success(f"✅ Loaded **{len(df)} rows** from `{uploaded_file.name}`. Your data is saved below.")
    except Exception as e:
        st.error(f"Could not read that CSV: {e}")

# --- Handle Crawl ---
if mode == "🕷️ Crawl a website" and start_button:
    if not target_url:
        st.error("Please enter a valid Start URL.")
    else:
        with st.spinner(f"Crawling {target_url}… This may take a few minutes depending on page count."):
            create_spider_script(target_url, max_pages_input, output_jsonl)

            result = subprocess.run(
                [sys.executable, "spider_script.py"],
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                st.error("Crawler failed. Here's the error from Scrapy:")
                st.code(result.stderr, language="bash")
            else:
                if os.path.exists(output_jsonl) and os.path.getsize(output_jsonl) > 0:
                    with open(output_jsonl, "r", encoding="utf-8") as f:
                        df = pd.read_json(io.StringIO(f.read()), lines=True)
                    st.session_state.crawl_df = df
                    st.session_state.crawl_source = "crawled"
                    st.success(f"✅ Crawl complete! Scraped **{len(df)} pages**. Results saved below.")
                else:
                    st.warning(
                        "The crawler finished but no pages were saved. "
                        "The site might be blocking the bot."
                    )

# ============================================================
# DISPLAY RESULTS (persists across re-runs)
# ============================================================
if st.session_state.crawl_df is not None:
    df = st.session_state.crawl_df
    source_label = "Crawled" if st.session_state.crawl_source == "crawled" else "Uploaded"

    st.divider()
    st.subheader(f"📊 SEO Audit Results — {len(df)} pages ({source_label})")
    st.caption(
        "Browse the table below. Click column headers to sort. "
        "Use the download button to save a copy as CSV."
    )

    # Quick stats row
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Pages", len(df))
    with col2:
        if "title" in df.columns:
            missing_titles = df["title"].isna().sum() + (df["title"] == "").sum()
            st.metric("Missing Titles", int(missing_titles))
    with col3:
        if "meta_desc" in df.columns:
            missing_meta = df["meta_desc"].isna().sum() + (df["meta_desc"] == "").sum()
            st.metric("Missing Meta Desc", int(missing_meta))

    st.dataframe(df, use_container_width=True)

    csv_data = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Download as CSV",
        data=csv_data,
        file_name="seo_audit.csv",
        mime="text/csv",
        type="primary",
    )
else:
    # Empty state
    st.info(
        "👈 **Choose an option in the sidebar** to get started:\n\n"
        "- **Crawl a website** — enter a URL and the crawler will follow internal links, "
        "extracting SEO metadata from each page.\n"
        "- **Upload a CSV** — load a previously downloaded crawl file to pick up where you left off."
    )
