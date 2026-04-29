import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

SOURCE_APP = "content_ct"
SOURCE_APP_VERSION = "1.0.0"
SCHEMA_VERSION = "linkup_export.v1"


def build_header(
    start_url: str,
    crawl_mode: str,
    max_pages: int,
    pages_crawled: int,
    exclude_paths: List[str],
    include_paths: List[str],
) -> dict:
    return {
        "kind": "header",
        "schema_version": SCHEMA_VERSION,
        "source_app": SOURCE_APP,
        "source_app_version": SOURCE_APP_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "start_url": start_url,
        "crawl_mode": crawl_mode,
        "max_pages": max_pages,
        "pages_crawled": pages_crawled,
        "exclude_paths": exclude_paths,
        "include_paths": include_paths,
    }


def build_export_jsonl(header_dict: dict, page_dicts: List[dict]) -> str:
    lines = [json.dumps(header_dict, ensure_ascii=False)]
    for page in page_dicts:
        lines.append(json.dumps(page, ensure_ascii=False))
    return "\n".join(lines)


def parse_export_jsonl(file_content: str) -> Tuple[Optional[dict], List[dict]]:
    header: Optional[dict] = None
    pages: List[dict] = []
    for line in file_content.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = obj.get("kind")
        if kind == "header":
            header = obj
        elif kind == "page":
            pages.append(obj)
    return header, pages
