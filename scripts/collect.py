"""Index research items listed by each institution on its own website."""
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")
HEADERS = {"User-Agent": "AIResearchRadar/1.0 (https://github.com/leeklim/ai-research-radar)"}


def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r


def day(raw):
    raw = raw.strip()
    for fmt in ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%d %B %Y"):
        try:
            return datetime.strptime(raw[:10] if fmt=="%Y-%m-%d" else raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def catalog(s):
    if s["id"]=="14":
        # This is the first-party content response used by the Qwen research page.
        for post in fetch("https://qwen.ai/api/page_config?code=research.research-list&language=en").json():
            if re.fullmatch(r"[\w.-]+",post["id"]):
                yield s["url"]+"/"+post["id"],post["title"],day(post.get("date",""))
        return
    page = fetch(s["url"])
    if urlsplit(page.url).hostname.removeprefix("www.") != urlsplit(s["url"]).hostname.removeprefix("www."):
        raise ValueError("등록된 기관 도메인 밖으로 이동")
    soup = BeautifulSoup(page.content,"html.parser")
    for row in soup.select(s["row"]):
        link = row.select_one(s["link"]) if "link" in s else row
        if not link or not link.has_attr("href"):
            continue
        href = urljoin(page.url,link["href"])
        if urlsplit(href).scheme not in ("https","http") or href.rstrip("/")==page.url.rstrip("/"):
            continue
        label = row if s.get("title")=="self" else row.select_one(s["title"]) if s.get("title") else (link.select_one("h2,h3,h4") or link)
        if not label:
            continue
        title = " ".join(label.stripped_strings)
        if s["id"]=="4" and title.lower()=="read the paper":
            title = urlsplit(href).path.rstrip("/").rsplit("/",1)[-1].replace("-"," ").capitalize()
        if len(title)<5 or len(title)>400 or re.fullmatch(r"[\W\d]*(?:authors?|comments?|paper|pdf|read more|view all|publication|research|publications)[\W\d]*",title,re.I):
            continue
        if s["id"]=="12":
            title += " Technical Report"
        date_tag = row.select_one(s["date"]) if s.get("date") else None
        published = day(date_tag.get("datetime") or date_tag.get_text(strip=True)) if date_tag else None
        if s["id"]=="15":
            published = day(href.rstrip("/")[-10:])
        if s["id"]=="28":
            # The BAIR Blog also carries events. Require a paper link in the post itself.
            body = BeautifulSoup(fetch(href).content,"html.parser")
            article = body.select_one(".post-content, article")
            if not article or not any(re.search(r"\b(?:paper|preprint|publication)\b",a.get_text(" ",strip=True),re.I)
                                      and re.search(r"arxiv\.org|openreview\.net|aclanthology\.org|proceedings\.mlr\.press",a["href"])
                                      for a in article.select("a[href]")):
                continue
            m = re.search(r"/blog/(\d{4})/(\d\d)/(\d\d)/",href)
            published = "-".join(m.groups()) if m else None
        yield href,title,published


def collect(s):
    rows = {}
    errors = []
    for listing in [s]+s.get("additional",[]):
        try:
            count = 0
            for url,title,published in catalog(dict(listing,id=s["id"])):
                rows.setdefault(url,(title,published,listing["url"]))
                count += 1
            if not count:
                errors.append("공식 목록에서 연구 링크를 확인하지 못함")
        except (requests.RequestException, ValueError) as exc:
            errors.append(str(exc)[:180])
    return s,rows," / ".join(errors)


def main():
    sources = json.loads((ROOT/"config/sources.json").read_text("utf8"))
    output = ROOT/"docs/data.json"
    old = {x["id"]:x for x in json.loads(output.read_text("utf8"))["items"]}
    lists = {s["id"]:{v["url"] for v in [s]+s.get("additional",[])} for s in sources}
    # Keep historical listings only if the official page was recorded as evidence.
    items = {k:v for k,v in old.items() if v.get("listed_on") in lists.get(v["source"],set())}
    status = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        for s, rows, error in pool.map(collect,sources):
            for url,(title,published,listing) in rows.items():
                key = hashlib.sha256((s["id"]+"|"+url.rstrip("/")).encode()).hexdigest()[:20]
                previous = old.get(key,{})
                items[key] = dict(id=key,source=s["id"],url=url,title=title,discovered=previous.get("discovered",NOW),
                                  published=published or previous.get("published"),listed_on=listing,kind="공식 연구 목록")
            status[s["id"]] = dict(ok=bool(rows),count=len(rows),partial=bool(rows and error),error=error or "")
            print(s["name"],len(rows),error or "",flush=True)
    ordered = sorted(items.values(),key=lambda x:x["published"] or "",reverse=True)
    tmp=output.with_suffix(".tmp")
    tmp.write_text(json.dumps(dict(updated=NOW,items=ordered,status=status),indent=2,ensure_ascii=False),"utf8")
    tmp.replace(output)


if __name__=="__main__":
    main()

