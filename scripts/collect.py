"""Index research items listed by each institution on its own website."""
import hashlib
import json
import re
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree
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
    raw = " ".join(raw.split())
    raw = re.sub(r"(?<=\d)(st|nd|rd|th)\b","",raw,flags=re.I)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}[T ].*",raw):
        raw = raw[:10]
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y", "%Y-%m", "%B %Y", "%b %Y", "%Y"):
        try:
            value = datetime.strptime(raw,fmt)
            if not 1900<=value.year<=2100:
                return None
            if fmt=="%Y":
                return value.strftime("%Y")
            if "%d" not in fmt:
                return value.strftime("%Y-%m")
            return value.date().isoformat()
        except ValueError:
            continue
    return None


def detail_date(soup,url):
    for tag in soup.select('meta[property="article:published_time"], meta[name="citation_publication_date"], meta[itemprop="datePublished"]'):
        date = day(tag.get("content",""))
        if date:
            return date
    host = urlsplit(url).hostname
    if host=="machinelearning.apple.com":
        label = soup.find("span",string=lambda s:s and s.strip().lower()=="published")
        if label:
            return day(str(label.next_sibling or ""))
    selectors = {
        "research.nvidia.com":".field--name-field-publication-date time[datetime]",
        "mistral.ai":"p.text-body-small.text-current",
        "www.csail.mit.edu":".news-top .field--name-field-publication-date time",
        "blog.eleuther.ai":".article-header .article-meta span:first-child",
        "mila.quebec":".group-blog-article-header .field-name-node-post-date",
    }
    if host in selectors:
        node=soup.select_one(selectors[host])
        if node:
            return day(node.get("datetime") or node.get_text(" ",strip=True))
    if host=="huggingface.co":
        node=soup.find(string=lambda t:t and t.strip().startswith("Published"))
        if node:
            return day(node.strip().removeprefix("Published"))
    if host=="crfm.stanford.edu":
        match=re.search(r"/(\d{4}/\d{2}/\d{2})/",urlsplit(url).path)
        if match:
            return day(match[1])
    # These sites put the publication date in the same header block as the title.
    if host in ("ai.meta.com","allenai.org","mistral.ai"):
        title=soup.find("h1")
        for parent in list(title.parents)[:3] if title else []:
            for text in parent.stripped_strings:
                date=day(text)
                if date and len(date)==10:
                    return date
    return None


def lookup_date(item):
    try:
        response=fetch(item["url"])
        if official_post(response.url,item["listed_on"]):
            return detail_date(BeautifulSoup(response.content,"html.parser"),response.url)
    except requests.RequestException:
        pass
    return None


def official_post(url, listing):
    dest = urlsplit(url)
    host = urlsplit(listing).hostname.removeprefix("www.")
    return (dest.scheme in ("http","https") and dest.hostname in (host,"www."+host)
            and dest.path.strip("/") and not dest.path.lower().endswith((".pdf",".zip",".xml"))
            and not (host=="huggingface.co" and not dest.path.startswith("/blog/huggingface/")))


def verify_html(url,listing):
    try:
        with requests.get(url, headers=HEADERS, timeout=8, stream=True) as response:
            if (response.ok and official_post(response.url,listing)
                    and "text/html" in response.headers.get("Content-Type","").lower()):
                return response.url
    except requests.RequestException:
        pass
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
    if s["id"]=="0":
        # The official index also lists products. Use the publisher's feed to label
        # only URLs actually present on that index and recover their publication dates.
        feed = ElementTree.fromstring(fetch("https://openai.com/news/rss.xml").content)
        research = {n.findtext("link","").rstrip("/"):n for n in feed.iter("item")
                    if n.findtext("category") in ("Research","Publication")}
        for anchor in soup.select(s["row"]):
            href = urljoin(page.url,anchor["href"])
            entry = research.get(href.rstrip("/"))
            if entry is not None:
                date = entry.findtext("pubDate")
                yield href,entry.findtext("title"),parsedate_to_datetime(date).date().isoformat() if date else None
        return
    for row in soup.select(s["row"]):
        if s["id"]=="16" and not re.match(r"^Research\s*·",row.get_text(" ",strip=True),re.I):
            continue
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
        date_tag = row.select_one(s["date"]) if s.get("date") else None
        published = day(date_tag.get("datetime") or date_tag.get_text(strip=True)) if date_tag else None
        if s["id"]=="13":
            published = next((date for t in row.select("footer *") if (date:=day(t.get_text(" ",strip=True)))),None)
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


def collect(s, old, cursor):
    rows = {}
    errors = []
    for listing in [s]+s.get("additional",[]):
        try:
            count = 0
            for url,title,published in catalog(dict(listing,id=s["id"])):
                if official_post(url,listing["url"]):
                    rows.setdefault(url,(title,published,listing["url"]))
                    count += 1
            if not count:
                errors.append("공식 목록에서 연구 링크를 확인하지 못함")
        except (requests.RequestException, ValueError, ElementTree.ParseError) as exc:
            errors.append(str(exc)[:180])
    verified = {}
    queue = []
    for url,(title,published,listing) in rows.items():
        key = hashlib.sha256((s["id"]+"|"+url.rstrip("/")).encode()).hexdigest()[:20]
        previous = old.get(key,{})
        if previous.get("official_html") and previous.get("listed_on")==listing:
            verified[url]=(title,published,listing,previous["url"])
        else:
            queue.append((url,title,published,listing))
    # Bound requests per institution. Future sweeps continue through the backlog.
    with ThreadPoolExecutor(max_workers=3) as checks:
        start = next((i for i,r in enumerate(queue) if r[0]==cursor),0)
        pending = queue[start:]+queue[:start]
        batch = pending[:60]
        for row,destination in zip(batch,checks.map(lambda r:verify_html(r[0],r[3]),batch)):
            if destination:
                url,title,published,listing=row
                verified[url]=(title,published,listing,destination)
    return s,verified," / ".join(errors),pending[60][0] if len(pending)>60 else None


def main():
    sources = json.loads((ROOT/"config/sources.json").read_text("utf8"))
    output = ROOT/"docs/data.json"
    snapshot = json.loads(output.read_text("utf8"))
    old = {x["id"]:x for x in snapshot["items"]}
    lists = {s["id"]:{v["url"] for v in [s]+s.get("additional",[])} for s in sources}
    # Keep historical listings only if the official page was recorded as evidence.
    items = {k:v for k,v in old.items() if v.get("official_html") and v.get("listed_on") in lists.get(v["source"],set()) and official_post(v["url"],v["listed_on"])}
    status = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        for s, rows, error, cursor in pool.map(lambda s:collect(s,old,snapshot["status"].get(s["id"],{}).get("next_url")),sources):
            for url,(title,published,listing,destination) in rows.items():
                key = hashlib.sha256((s["id"]+"|"+url.rstrip("/")).encode()).hexdigest()[:20]
                previous = old.get(key,{})
                items[key] = dict(id=key,source=s["id"],url=destination,title=title,discovered=previous.get("discovered",NOW),
                                  published=published or previous.get("published"),listed_on=listing,official_html=True,kind="공식 연구 게시글")
            status[s["id"]] = dict(ok=bool(rows),count=len(rows),partial=bool(rows and error),error=error or "",next_url=cursor)
            print(s["name"],len(rows),error or "",flush=True)
    undated=[item for item in items.values() if not item["published"]]
    with ThreadPoolExecutor(max_workers=6) as pool:
        for item,date in zip(undated,pool.map(lookup_date,undated)):
            item["published"]=date
    ordered = sorted(items.values(),key=lambda x:x["published"] or "",reverse=True)
    tmp=output.with_suffix(".tmp")
    tmp.write_text(json.dumps(dict(updated=NOW,items=ordered,status=status),indent=2,ensure_ascii=False),"utf8")
    tmp.replace(output)


if __name__=="__main__":
    main()

