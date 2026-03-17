import streamlit as st
import pandas as pd
import os
import io
import subprocess
from urllib.parse import urlparse
from scrapy.linkextractors import IGNORED_EXTENSIONS

# --- 1. SET PAGE CONFIG ---
st.set_page_config(page_title="Healthcare SEO Crawler", page_icon="🕷️", layout="wide")

# --- 2. DEFINE BANNED EXTENSIONS ---
# Stop the crawler from downloading raw data files, zips, or medical documents
banned_extensions = IGNORED_EXTENSIONS + ['gz', 'txt', 'zip', 'csv', 'pdf', 'docx', 'xlsx', 'tar']

# --- 3. SCRAPY SPIDER SCRIPT GENERATOR ---
# Because Streamlit and Scrapy's "Twisted" engine don't like running in the same thread,
# we generate the spider as a separate python file and run it safely.
def create_spider_script(start_url, max_pages, output_file):
    domain = urlparse(start_url).netloc
    
    # Safely handle the page count setting to prevent the "None" string crash
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
    
    # 1. FILE DOWNLOAD FIX: Tell the LinkExtractor to ignore data files
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
        'DOWNLOAD_MAXSIZE': 5242880, # Hard cap at 5MB to stop giant .gz file downloads
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
    
    # We use a number input here so it defaults to 0 (which we will treat as unlimited)
    # This prevents the user from typing "None" or letters.
    max_pages_input = st.number_input("Max Pages to Crawl (0 = Unlimited)", min_value=0, value=50, step=10)
    
    start_button = st.button("🚀 Start Crawl", type="primary", use_container_width=True)

# --- 5. EXECUTION LOGIC ---
output_jsonl = "crawl_output.jsonl"

if start_button:
    if not target_url:
        st.error("Please enter a valid Start URL.")
    else:
        with st.spinner(f"Crawling {target_url}... This may take a few minutes depending on page count."):
            # 1. Generate the safe spider script
            create_spider_script(target_url, max_pages_input, output_jsonl)
            
            # 2. Run the spider safely in a subprocess
            try:
                subprocess.run(["python", "spider_script.py"], check=True)
                
                # 3. Check if output exists
                if os.path.exists(output_jsonl) and os.path.getsize(output_jsonl) > 0:
                    
                    # 4. PANDAS FIX: Use io.StringIO to read the file safely
                    with open(output_jsonl, 'r', encoding='utf-8') as f:
                        df = pd.read_json(io.StringIO(f.read()), lines=True)
                    
                    st.success(f"✅ Crawl complete! Successfully scraped {len(df)} pages.")
                    
                    # 5. Display the data
                    st.subheader("📊 Crawl Results")
                    st.dataframe(df, use_container_width=True)
                    
                    # 6. CSV Download Button
                    csv_data = df.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📥 Download Data as CSV",
                        data=csv_data,
                        file_name="columbia_seo_audit.csv",
                        mime="text/csv",
                        type="primary"
                    )
                else:
                    st.warning("The crawler finished, but no pages were saved. The site might be blocking the bot.")
            except subprocess.CalledProcessError as e:
                st.error(f"Crawler failed to run. Error: {e}")
