import streamlit as st
import pandas as pd
import os
import io
import sys
import subprocess
import json
import requests
from bs4 import BeautifulSoup
from collections import deque
from urllib.parse import urlparse, urljoin, urldefrag
# --- 1. SET PAGE CONFIG ---
st.set_page_config(page_title="Healthcare SEO Crawler", page_icon="🕷️", layout="wide")

# --- 2. DEFINE BANNED EXTENSIONS ---
# Use a conservative set of common non-HTML extensions to avoid relying on Scrapy-specific constants.
banned_extensions = ['7z', 'gz', 'txt', 'zip', 'csv', 'pdf', 'docx', 'xlsx', 'tar', 'png', 'jpg', 'jpeg', 'gif', 'svg', 'css', 'js']

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
            LinkExtractor(deny_extensions={repr(banned_extensions)}), 
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


def crawl_with_requests(start_url, max_pages, output_file, banned_extensions):
    """Lightweight fallback crawler using requests + BeautifulSoup.
    Writes results to `output_file` in JSON Lines format.
    """
    domain = urlparse(start_url).netloc
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'} )

    q = deque([start_url])
    visited = set()
    scraped = 0

    with open(output_file, 'w', encoding='utf-8') as out_f:
        while q and (scraped < int(max_pages) or int(max_pages) == 0):
            url = q.popleft()
            url, _ = urldefrag(url)
            if url in visited:
                continue

            parsed = urlparse(url)
            if parsed.scheme not in ('http', 'https'):
                continue

            # keep in-domain only
            if parsed.netloc and not parsed.netloc.endswith(domain):
                continue

            # skip common non-html extensions
            path_ext = os.path.splitext(parsed.path)[1].lower().lstrip('.')
            if path_ext and path_ext in banned_extensions:
                continue

            try:
                resp = session.get(url, timeout=12)
            except Exception:
                visited.add(url)
                continue

            visited.add(url)
            status = getattr(resp, 'status_code', None) or 0

            if resp.status_code != 200 or not resp.text:
                out_f.write(json.dumps({'url': url, 'status': status, 'title': '', 'h1': '', 'meta_desc': '', 'word_count': 0}, ensure_ascii=False) + "\n")
                continue

            soup = BeautifulSoup(resp.text, 'html.parser')
            title = soup.title.string.strip() if soup.title and soup.title.string else ''
            first_h1 = soup.find('h1')
            h1 = first_h1.get_text(strip=True) if first_h1 else ''
            meta_tag = soup.find('meta', attrs={'name': 'description'})
            meta_desc = (meta_tag.get('content') or '').strip() if meta_tag else ''
            body = soup.find('body')
            text = body.get_text(separator=' ', strip=True) if body else ''
            word_count = len(text.split()) if text else 0

            out_f.write(json.dumps({'url': url, 'status': status, 'title': title, 'h1': h1, 'meta_desc': meta_desc, 'word_count': word_count}, ensure_ascii=False) + "\n")
            scraped += 1

            # enqueue links
            for a in soup.find_all('a', href=True):
                href = a['href']
                joined = urljoin(url, href)
                joined, _ = urldefrag(joined)
                p2 = urlparse(joined)
                if p2.scheme not in ('http', 'https'):
                    continue
                if p2.netloc and not p2.netloc.endswith(domain):
                    continue
                ext2 = os.path.splitext(p2.path)[1].lower().lstrip('.')
                if ext2 and ext2 in banned_extensions:
                    continue
                if joined not in visited:
                    q.append(joined)

# --- 4. APP LAYOUT & UI ---
st.title("🕷️ Live SEO Crawler")
st.markdown("Crawl the Columbia site to extract titles, H1s, and Meta Descriptions.")

with st.sidebar:
    st.header("⚙️ Crawler Settings")
    target_url = st.text_input("Start URL", value="https://www.columbiamedicine.org/")
    max_pages_input = st.number_input("Max Pages to Crawl (0 = Unlimited)", min_value=0, value=50, step=10)
    start_button = st.button("🚀 Start Crawl", use_container_width=True)

# --- 5. EXECUTION LOGIC ---
output_jsonl = "crawl_output.jsonl"

if start_button:
    if not target_url:
        st.error("Please enter a valid Start URL.")
    else:
        with st.spinner(f"Crawling {target_url}... This may take a few minutes depending on page count."):
            # Prefer Scrapy if available; otherwise use the lightweight fallback crawler
            try:
                import scrapy  # type: ignore
            except ModuleNotFoundError:
                st.info("Scrapy not installed — running lightweight fallback crawler (requests + BeautifulSoup).")
                try:
                    crawl_with_requests(target_url, max_pages_input, output_jsonl, banned_extensions)
                except Exception as e:
                    st.error(f"Fallback crawler failed: {e}")
            else:
                create_spider_script(target_url, max_pages_input, output_jsonl)
                result = subprocess.run(
                    [sys.executable, "spider_script.py"], 
                    capture_output=True, 
                    text=True
                )
                if result.returncode != 0:
                    st.error("Crawler failed to run. Here is the exact error from Scrapy:")
                    st.code(result.stderr, language="bash")

            # show results if output produced
            if os.path.exists(output_jsonl) and os.path.getsize(output_jsonl) > 0:
                with open(output_jsonl, 'r', encoding='utf-8') as f:
                    df = pd.read_json(io.StringIO(f.read()), lines=True)

                st.success(f"✅ Crawl complete! Successfully scraped {len(df)} pages.")
                st.subheader("📊 Crawl Results")
                st.dataframe(df, use_container_width=True)

                csv_data = df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="Download Data as CSV",
                    data=csv_data,
                    file_name="columbia_seo_audit.csv",
                    mime="text/csv"
                )
            else:
                st.warning("The crawler finished successfully, but no pages were saved. The site might be blocking the bot or no HTML pages were found.")

