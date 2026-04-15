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
            LinkExtractor(
                deny_extensions={repr(banned_extensions)},
                deny=[r'/file/\\d+/download']
            ),
            callback='parse_item',
            follow=True
        ),
    )

    custom_settings = {{
        'USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'ROBOTSTXT_OBEY': False,
        'DOWNLOAD_MAXSIZE': 5242880,
        'LOG_LEVEL': 'INFO',
        'DEPTH_PRIORITY': 1,
        'SCHEDULER_DISK_QUEUE': 'scrapy.squeues.PickleFifoDiskQueue',
        'SCHEDULER_MEMORY_QUEUE': 'scrapy.squeues.FifoMemoryQueue',
        {page_limit_code}
        'FEEDS': {{
            '{output_file}': {{'format': 'jsonlines', 'overwrite': True}}
        }}
    }}

    def parse_item(self, response):
        if not hasattr(response, 'css'):
            return
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
    domain = urlparse(start_url).netloc
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
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
            if parsed.netloc and not parsed.netloc.endswith(domain):
                continue
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
            for a in soup.find_all('a', href=True):
                joined = urljoin(url, a['href'])
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


# --- 4. SEO ISSUE DETECTION ---
def detect_seo_issues(df):
    dup_titles = set(df['title'][df['title'].str.strip() != ''].value_counts()[lambda x: x > 1].index)
    dup_metas  = set(df['meta_desc'][df['meta_desc'].str.strip() != ''].value_counts()[lambda x: x > 1].index)

    rows = []
    for _, row in df.iterrows():
        issues = []
        title = str(row.get('title', '') or '')
        meta  = str(row.get('meta_desc', '') or '')
        h1    = str(row.get('h1', '') or '')
        wc    = int(row.get('word_count', 0) or 0)
        status = int(row.get('status', 200) or 200)

        if not title:
            issues.append('Missing title')
        elif len(title) < 30:
            issues.append(f'Title too short ({len(title)} chars, min 30)')
        elif len(title) > 60:
            issues.append(f'Title too long ({len(title)} chars, max 60)')
        if title in dup_titles:
            issues.append('Duplicate title')

        if not meta:
            issues.append('Missing meta description')
        elif len(meta) < 50:
            issues.append(f'Meta desc too short ({len(meta)} chars, min 50)')
        elif len(meta) > 160:
            issues.append(f'Meta desc too long ({len(meta)} chars, max 160)')
        if meta in dup_metas:
            issues.append('Duplicate meta description')

        if not h1:
            issues.append('Missing H1')

        if wc < 300:
            issues.append(f'Low word count ({wc} words)')

        if status not in (200, 301, 302):
            issues.append(f'HTTP {status}')

        rows.append({
            'url': row['url'],
            'status': status,
            'title': title,
            'h1': h1,
            'meta_desc': meta,
            'word_count': wc,
            'issues': '; '.join(issues),
            'issue_count': len(issues),
        })

    return pd.DataFrame(rows)


# --- 5. GEMINI AI CORRECTIONS ---
def call_gemini(prompt, api_key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    resp = requests.post(url, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()['candidates'][0]['content']['parts'][0]['text']


def build_gemini_prompt(issues_df):
    lines = ["You are an SEO expert. For each page below, suggest a corrected title and meta description that fix the listed issues. Be concise and specific to healthcare/medical content.\n"]
    for _, row in issues_df.iterrows():
        lines.append(f"URL: {row['url']}")
        lines.append(f"Current title: {row['title'] or '(none)'}")
        lines.append(f"Current meta desc: {row['meta_desc'] or '(none)'}")
        lines.append(f"Current H1: {row['h1'] or '(none)'}")
        lines.append(f"Issues: {row['issues']}")
        lines.append("---")
    lines.append("\nFor each URL provide:\n- Suggested title (30-60 chars)\n- Suggested meta description (50-160 chars)\n- One-line reason for each change")
    return "\n".join(lines)


# --- 6. APP LAYOUT & UI ---
st.title("🕷️ Live SEO Crawler")
st.markdown("Crawl a site, detect SEO issues, and get AI-powered correction suggestions.")

if 'df' not in st.session_state:
    st.session_state.df = None
if 'issues_df' not in st.session_state:
    st.session_state.issues_df = None
if 'gemini_response' not in st.session_state:
    st.session_state.gemini_response = None

with st.sidebar:
    st.header("⚙️ Crawler Settings")
    target_url = st.text_input("Start URL", value="https://vagelos.columbia.edu")
    max_pages_input = st.number_input("Max Pages to Crawl (0 = Unlimited)", min_value=0, value=50, step=10)
    start_button = st.button("🚀 Start Crawl", use_container_width=True)
    st.divider()
    st.header("🤖 Gemini Settings")
    gemini_key = st.text_input("Gemini API Key", type="password",
                                value=os.environ.get("GEMINI_API_KEY", ""),
                                help="Set GEMINI_API_KEY in HF Secrets or paste here")

# --- 7. CRAWL EXECUTION ---
output_jsonl = "crawl_output.jsonl"

if start_button:
    if not target_url:
        st.error("Please enter a valid Start URL.")
    else:
        st.session_state.df = None
        st.session_state.issues_df = None
        st.session_state.gemini_response = None

        with st.spinner(f"Crawling {target_url}..."):
            try:
                import scrapy  # type: ignore
            except ModuleNotFoundError:
                st.info("Scrapy not available — using fallback crawler.")
                try:
                    crawl_with_requests(target_url, max_pages_input, output_jsonl, banned_extensions)
                except Exception as e:
                    st.error(f"Fallback crawler failed: {e}")
            else:
                create_spider_script(target_url, max_pages_input, output_jsonl)
                result = subprocess.run([sys.executable, "spider_script.py"], capture_output=True, text=True)
                if result.returncode != 0:
                    st.error("Scrapy failed:")
                    st.code(result.stderr, language="bash")

        if os.path.exists(output_jsonl) and os.path.getsize(output_jsonl) > 0:
            with open(output_jsonl, 'r', encoding='utf-8') as f:
                st.session_state.df = pd.read_json(io.StringIO(f.read()), lines=True)
            st.session_state.issues_df = detect_seo_issues(st.session_state.df)

# --- 8. DISPLAY RESULTS ---
if st.session_state.df is not None:
    df = st.session_state.df
    issues_df = st.session_state.issues_df

    tab1, tab2, tab3 = st.tabs(["📊 All Pages", "⚠️ SEO Issues", "🤖 Gemini Suggestions"])

    with tab1:
        st.success(f"✅ Crawled {len(df)} pages.")
        st.dataframe(df, use_container_width=True)
        st.download_button("Download CSV", df.to_csv(index=False).encode('utf-8'),
                           file_name="crawl_results.csv", mime="text/csv")

    with tab2:
        flagged = issues_df[issues_df['issue_count'] > 0].sort_values('issue_count', ascending=False)
        clean   = issues_df[issues_df['issue_count'] == 0]

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Pages", len(issues_df))
        col2.metric("Pages with Issues", len(flagged))
        col3.metric("Clean Pages", len(clean))
        col4.metric("Total Issues", issues_df['issue_count'].sum())

        if len(flagged):
            # Issue type breakdown
            all_issues = '; '.join(flagged['issues'].tolist())
            issue_types = {}
            for chunk in all_issues.split('; '):
                chunk = chunk.strip()
                if chunk:
                    # Normalize variable counts to category
                    key = chunk.split('(')[0].strip()
                    issue_types[key] = issue_types.get(key, 0) + 1
            st.subheader("Issue Breakdown")
            st.dataframe(pd.DataFrame(list(issue_types.items()), columns=['Issue', 'Count']).sort_values('Count', ascending=False), use_container_width=True, hide_index=True)

            st.subheader("Flagged Pages")
            st.dataframe(flagged[['url', 'title', 'meta_desc', 'h1', 'word_count', 'issues']],
                         use_container_width=True, hide_index=True)
            st.download_button("Download Issues CSV",
                               flagged.to_csv(index=False).encode('utf-8'),
                               file_name="seo_issues.csv", mime="text/csv")
        else:
            st.success("No SEO issues found!")

    with tab3:
        flagged = issues_df[issues_df['issue_count'] > 0]
        if flagged.empty:
            st.info("No issues found — nothing for Gemini to fix.")
        else:
            st.markdown(f"**{len(flagged)} pages with issues** ready for AI analysis.")
            max_pages_gemini = st.slider("Pages to send to Gemini (most issues first)", 1, min(len(flagged), 20), min(5, len(flagged)))
            analyze_button = st.button("✨ Analyze with Gemini", use_container_width=True)

            if analyze_button:
                if not gemini_key:
                    st.error("Add your Gemini API key in the sidebar or set GEMINI_API_KEY in HF Secrets.")
                else:
                    top_pages = flagged.head(max_pages_gemini)
                    prompt = build_gemini_prompt(top_pages)
                    with st.spinner("Asking Gemini for corrections..."):
                        try:
                            st.session_state.gemini_response = call_gemini(prompt, gemini_key)
                        except Exception as e:
                            st.error(f"Gemini API error: {e}")

            if st.session_state.gemini_response:
                st.subheader("Gemini's Suggested Corrections")
                st.markdown(st.session_state.gemini_response)
                st.download_button("Download Suggestions",
                                   st.session_state.gemini_response.encode('utf-8'),
                                   file_name="gemini_suggestions.txt", mime="text/plain")
