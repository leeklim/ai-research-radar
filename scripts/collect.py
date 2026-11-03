"""Index research items listed by each institution on its own website."""
import hashlib
import json
import re
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
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y", "%B %d '%y", "%b %d '%y", "%m/%d/%Y", "%Y-%m", "%B %Y", "%b %Y", "%Y"):
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
    host = urlsplit(url).hostname.removeprefix("www.")
    selectors = {
        "openai.com": "main .text-meta",
        "anthropic.com": "article time,main time",
        "deepmind.google": ".section-title__date",
        "goodfire.com": ".article-kicker time,article header time",
        "microsoft.com": "time[datetime]",
        "research.nvidia.com": ".field--name-field-publication-date time",
        "research.ibm.com": "main time",
        "salesforce.com": ".hero-byline__date",
        "amazon.science": ".PublicationDetailPage-publicationDate",
        "deepseek.com": "p.ds-text-caption .text-ds-description",
        "mistral.ai": "p.text-body-small.text-current",
        "cohere.com": "main p[class*=eyebrow]",
        "ai21.com": ".post-date",
        "liquid.ai": "main time",
        "sakana.ai": "article header time,header time",
        "thinkingmachines.ai": ".publish-metadata span",
        "redwoodresearch.org": ".hf-report-byline p,.hf-report-meta",
        "apolloresearch.ai": ".paper-right_published p",
        "blog.eleuther.ai": ".article-header .article-meta span:first-child",
        "jina.ai": ".q-item__label--caption.text-center",
        "bair.berkeley.edu": ".post-header .post-meta",
        "csail.mit.edu": ".news-top .field--name-field-publication-date time",
        "blog.ml.cmu.edu": ".date",
        "mila.quebec": ".group-blog-article-header .field-name-node-post-date",
    }
    if host=="machinelearning.apple.com":
        tag=soup.find("span",string=lambda t:t and t.strip().lower()=="published")
        if tag:
            return day(str(tag.next_sibling or ""))
    if host=="huggingface.co":
        label=soup.find(string=lambda t:t and t.strip().startswith("Published"))
        return day(label.strip().removeprefix("Published")) if label else None
    for node in soup.select(selectors[host]) if host in selectors else []:
        for text in node.stripped_strings:
            text = re.sub(r"^(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s*", "",text,flags=re.I)
            date = day(text.split(" · ")[0])
            if date:
                return date
    if host in ("ai.meta.com","allenai.org","seed.bytedance.com"):
        heading=soup.find("h1")
        for parent in list(heading.parents)[:3] if heading else []:
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
    if s.get("team"):
        # Featured work is not always present in the team's paginated list.
        soup=BeautifulSoup(fetch(s["url"]).content,"html.parser")
        for a in soup.select("main a[href]:has(h2),main h2 a[href]"):
            title=a.select_one("h2") or a
            url=urljoin(s["url"],a["href"])
            if urlsplit(url).path.startswith(("/research/","/institute/")) and "/team/" not in url:
                yield url,title.get_text(" ",strip=True),None
        page=1
        while True:
            endpoint=f"https://www.anthropic.com/listing/{s['feed']}/default/{page}"
            data=fetch(endpoint).json()
            for post in data["posts"]:
                path=post.get("linkedUrl")
                slug=(post.get("slug") or {}).get("current")
                if not path and slug and post.get("articleType") in ("research","engineering","institute","news"):
                    path=f"/{post['articleType']}/{slug}"
                if path and post.get("title"):
                    yield urljoin(s["url"],path),post["title"].strip(),day(post.get("publishedOn") or "")
            if not data["hasNextPage"]:
                break
            page+=1
        return
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
                yield href,entry.findtext("title"),next((date for text in anchor.stripped_strings if (date:=day(text))),None)
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
        published = day(date_tag.get_text(" ",strip=True)) if date_tag else None
        if s["id"]=="13":
            published = next((date for t in row.select("footer *") if (date:=day(t.get_text(" ",strip=True)))),None)
        if s["id"]=="27":
            card=row.find_parent("div",class_="item")
            if card:
                published=next((date for text in card.stripped_strings if (date:=day(text))),None)
        if s["id"]=="28":
            # The BAIR Blog also carries events. Require a paper link in the post itself.
            body = BeautifulSoup(fetch(href).content,"html.parser")
            article = body.select_one(".post-content, article")
            if not article or not any(re.search(r"\b(?:paper|preprint|publication)\b",a.get_text(" ",strip=True),re.I)
                                      and re.search(r"arxiv\.org|openreview\.net|aclanthology\.org|proceedings\.mlr\.press",a["href"])
                                      for a in article.select("a[href]")):
                continue

        yield href,title,published


def collect(s, old, cursor):
    rows = {}
    errors = []
    memberships = {}
    for listing in listings(s):
        try:
            count = 0
            for url,title,published in catalog(dict(listing,id=s["id"])):
                if official_post(url,listing["url"]):
                    if listing.get("team"):
                        memberships.setdefault(url,{})[listing["team"]]=listing["url"]
                    if url not in rows or (published and not rows[url][1]):
                        rows[url]=(title,published,listing["url"])
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
        batch = pending if memberships else pending[:60]
        for row,destination in zip(batch,checks.map(lambda r:verify_html(r[0],r[3]),batch)):
            if destination:
                url,title,published,listing=row
                verified[url]=(title,published,listing,destination)
    return s,verified," / ".join(errors),pending[len(batch)][0] if len(pending)>len(batch) else None,memberships


def listings(s):
    return s["additional"] if s["id"]=="1" else [s]+s.get("additional",[])


def main():
    sources = json.loads((ROOT/"config/sources.json").read_text("utf8"))
    output = ROOT/"docs/data.json"
    snapshot = json.loads(output.read_text("utf8"))
    old = {x["id"]:x for x in snapshot["items"]}
    lists = {s["id"]:{v["url"] for v in listings(s)} for s in sources}
    # Keep historical listings only if the official page was recorded as evidence.
    items = {k:v for k,v in old.items() if v.get("official_html") and v.get("listed_on") in lists.get(v["source"],set()) and official_post(v["url"],v["listed_on"])}
    status = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        for s, rows, error, cursor, memberships in pool.map(lambda s:collect(s,old,snapshot["status"].get(s["id"],{}).get("next_url")),sources):
            for url,(title,published,listing,destination) in rows.items():
                key = hashlib.sha256((s["id"]+"|"+url.rstrip("/")).encode()).hexdigest()[:20]
                previous = old.get(key,{})
                items[key] = dict(previous,id=key,source=s["id"],url=destination,title=title,discovered=previous.get("discovered",NOW),
                                  listing_date=published or previous.get("listing_date"),published=previous.get("published"),listed_on=listing,official_html=True,kind="공식 연구 게시글")
                if url in memberships:
                    previous_teams={team:page for team,page in previous.get("teams",{}).items() if page in lists[s["id"]]}
                    items[key]["teams"]={**previous_teams,**memberships[url]}
            status[s["id"]] = dict(ok=bool(rows),count=len(rows),partial=bool(rows and error),error=error or "",next_url=cursor)
            print(s["name"],len(rows),error or "",flush=True)
    pending=[item for item in items.values() if item.get("date_basis")!="상세 글"]
    with ThreadPoolExecutor(max_workers=6) as pool:
        for item,date in zip(pending,pool.map(lookup_date,pending)):
            item["published"]=date or item.get("listing_date")
            item["date_basis"]="상세 글" if date else "공식 목록" if item["published"] else None
    ordered = sorted(items.values(),key=lambda x:x["published"] or "",reverse=True)
    tmp=output.with_suffix(".tmp")
    tmp.write_text(json.dumps(dict(updated=NOW,items=ordered,status=status),indent=2,ensure_ascii=False),"utf8")
    tmp.replace(output)


if __name__=="__main__":
    main()

