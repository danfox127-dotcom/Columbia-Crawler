import streamlit as st
import pandas as pd
import os
import io
import sys
import subprocess
from urllib.parse import urlparse
from scrapy.linkextractors import IGNORED_EXTENSIONS

# --- 1. SET PAGE CONFIG ---
st.set_page_config(page_title="Healthcare SEO Crawler", page_icon="🕷️", layout="wide")

# --- 2. DEFINE BANNED EXTENSIONS ---
banned_extensions = IGNORED_EXTENSIONS + ['gz', 'txt', 'zip', 'csv', 'pdf', 'docx', 'xlsx', 'tar']

# --- 3. SCRAPY SPIDER SCRIPT GENERATOR ---
def create_spider_script(start_url, max_pages, output_file):
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
        'USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
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
    with open("spider_script.py", "w") as f:
        f.write(script_content)

# --- 4. APP LAYOUT & UI ---
st.title("🕷️ Live SEO Crawler")
st.markdown("Crawl the Columbia site to extract titles, H1s, and Meta Descriptions. Now equipped with safe-download limits and extension blocking.")

with st.sidebar:
    st.header("⚙️ Crawler Settings")
    target_url = st.text_input("Start URL", value="https://www.columbiamedicine.org/")
    max_pages_input = st.number_input("Max Pages to Crawl (0 = Unlimited)", min_value=0, value=50, step=10)
    start_button = st.button("🚀 Start Crawl", type="primary", use_container_width=True)

# --- 5. EXECUTION LOGIC ---
output_jsonl = "crawl_output.jsonl"

if start_button:
    if not target_url:
        st.error("Please enter a valid Start URL.")
    else:
        with st.spinner(f"Crawling {target_url}... This may take a few minutes depending on page count."):
            create_spider_script(target_url, max_pages_input, output_jsonl)
            
            # Use sys.executable to guarantee we use the right Python environment
            # Use capture_output=True so we can read the actual Scrapy error if it fails
            result = subprocess.run(
                [sys.executable, "spider_script.py"], 
                capture_output=True, 
                text=True
            )
            
            if result.returncode != 0:
                st.error("Crawler failed to run. Here is the exact error from Scrapy:")
                # Print the raw error trace so we know exactly what went wrong
                st.code(result.stderr, language="bash")
            else:
                if os.path.exists(output_jsonl) and os.path.getsize(output_jsonl) > 0:
                    with open(output_jsonl, 'r', encoding='utf-8') as f:
                        df = pd.read_json(io.StringIO(f.read()), lines=True)
                    
                    st.success(f"✅ Crawl complete! Successfully scraped {len(df)} pages.")
                    st.subheader("📊 Crawl Results")
                    st.dataframe(df, use_container_width=True)
                    
                    csv_data = df.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="
