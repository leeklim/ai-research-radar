"""Index research items listed by each institution on its own website."""
import hashlib
import json
import re
from xml.etree import ElementTree
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, parse_qsl, urlencode, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup
from editorial_quality import REVIEWED, PROMOTIONAL, GUIDE_OR_NEWS_SUMMARY, exclusion_reason
from ibm_publication import ibm_evidence, ibm_research_paper
import snapshot as catalog_snapshot

ROOT = Path(__file__).resolve().parents[1]
REVIEWED_URLS = json.loads((ROOT/"config/reviewed_nonresearch.json").read_text("utf8"))
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")
HEADERS = {"User-Agent": "AIResearchRadar/1.0 (https://github.com/leeklim/ai-research-radar)"}
MILA_PUBLICATIONS = "https://mila.quebec/en/research/publications"
JINA_NEWS = "https://jina.ai/news/"



def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r


def day(raw):
    raw = " ".join(raw.split())
    raw = re.sub(r"(?<=\d)(st|nd|rd|th)\b","",raw,flags=re.I)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}[T ].*",raw):
        raw = raw[:10]
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y", "%B %d '%y", "%b %d '%y", "%m/%d/%Y", "%m/%d/%y", "%Y-%m", "%B %Y", "%b %Y", "%Y"):
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
    for time_tag in soup.select("article header time, .post-header time, .article-header time"):
        date=day(time_tag.get_text(" ",strip=True))
        if date:
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
    if host=="research.ibm.com":
        return (listing.rstrip("/")=="https://research.ibm.com/publications"
                and dest.scheme=="https" and dest.netloc=="research.ibm.com"
                and bool(re.fullmatch(r"/publications/[^/]+/?",dest.path)))
    return (dest.scheme in ("http","https") and dest.hostname in (host,"www."+host)
            and dest.path.strip("/") and not dest.path.lower().endswith((".pdf",".zip",".xml"))
            and (host!="huggingface.co" or dest.path.startswith("/blog/huggingface/")
                 or (listing=="https://huggingface.co/blog?tag=research" and re.fullmatch(r"/blog/[\w-]+",dest.path))))


def openreview_id(url):
    dest=urlsplit(url)
    ids=parse_qs(dest.query).get("id",[])
    if (dest.scheme=="https" and dest.netloc=="openreview.net" and dest.path in ("/forum","/pdf")
            and len(ids)==1 and re.fullmatch(r"[\w-]+",ids[0])):
        return ids[0]
    return None


def paper_target(url,listing):
    dest=urlsplit(url)
    if listing.get("adapter")=="openai_publications" and dest.hostname not in ("openai.com","www.openai.com"):
        # Only the exact Publication index component can emit an external card.
        return dest.scheme=="https" and bool(dest.hostname)
    pattern=listing.get("paper_links",{}).get(dest.netloc)
    if not pattern or dest.scheme not in ("https","http") or not re.fullmatch(pattern,dest.path):
        return False
    if dest.netloc=="openreview.net":
        return (openreview_id(url) is not None or bool(re.fullmatch(r"/pdf/[a-f0-9]{40,64}\.pdf",dest.path))
                or dest.path=="/attachment" and parse_qs(dest.query).get("name")==["pdf"]
                and bool(re.fullmatch(r"[\w-]+",parse_qs(dest.query).get("id",[""])[0])))
    return True


def eligible_link(url,listing):
    return paper_target(url,listing) or (not listing.get("papers_only") and official_post(url,listing["url"]))


def keep_research(source,url,title,summary=""):
    if source=="0":return True
    path=urlsplit(url).path.rstrip("/")
    if url.rstrip("/") in REVIEWED_URLS or (source,path) in REVIEWED:
        return False
    if source=="5" and re.match(r"^(?:proceedings (?:of|from) (?:the |a |an |[0-9])|call for (?:papers|participation)\b|table of contents\b|author index\b|message from the (?:chairs|editors)\b|(?:preface|foreword)(?:$| to (?:the |this )?(?:proceedings|special issue)))",title,re.I):
        return False
    if source not in ("0","1","10","17","20","21"):
        return True
    if not PROMOTIONAL.search(title) and not GUIDE_OR_NEWS_SUMMARY.search(summary.strip()):
        return True
    try:
        response=fetch(url)
        soup=BeautifulSoup(response.content,"html.parser")
        article=soup.select_one("main article,article,main")
        if not article:
            return False
        for tag in article.select("aside, footer, nav, script, style"):
            tag.decompose()
        body=article.get_text(" ",strip=True)
    except requests.RequestException:
        return False
    # Use the same evidence threshold on additional mixed editorial feeds.
    return exclusion_reason(dict(source=source,url=url,title=title),
                            summary,body) is None


def verify_ibm_item(item):
    try:
        response=fetch(item["url"])
    except requests.RequestException:
        return None
    evidence=ibm_evidence(BeautifulSoup(response.content,"html.parser"),response.url)
    if not ibm_research_paper(evidence):
        return False
    item.update(publication_type=evidence["kind"],venue=evidence["venue"],ibm_verified=True)
    return True


def verify_destination(url,listing):
    try:
        for _ in range(5):
            if paper_target(url,listing):
                return url
            if not official_post(url,listing["url"]):
                break
            with requests.get(url,headers=HEADERS,timeout=8,stream=True,allow_redirects=False) as response:
                if response.is_redirect:
                    url=urljoin(url,response.headers["Location"])
                    continue
                if response.ok and not listing.get("papers_only") and "text/html" in response.headers.get("Content-Type","").lower():
                    return response.url
                break
    except requests.RequestException:
        pass
    return None


def article_id(source_id,url):
    # Preserve bookmarks from the original Qwen link format while replacing
    # its home-page redirects with the URL opened by the research card.
    parsed=urlsplit(url)
    if source_id=="14" and parsed.path.rstrip("/")=="/blog":
        slug=parse_qs(parsed.query).get("id",[""])[0]
        if slug:
            url="https://qwen.ai/research/"+slug
    if source_id=="31" and openreview_id(url):
        url="https://openreview.net/forum?id="+openreview_id(url)
    return hashlib.sha256((source_id+"|"+url.rstrip("/")).encode()).hexdigest()[:20]


def catalog(s):
    if s.get("adapter")=="ai2_research":
        page=s["url"]
        seen=set()
        while page:
            if page in seen or urlsplit(page).hostname!="allenai.org" or urlsplit(page).path!="/research":
                raise ValueError("Ai2 Research 다음 페이지 주소 확인 실패")
            seen.add(page)
            soup=BeautifulSoup(fetch(page).content,"html.parser")
            cards=soup.select("main a[href]:has(h2)")
            if not cards:raise ValueError("Ai2 Research 카드 확인 실패")
            s["found_on"]=page
            for link in cards:
                card=next((p for p in link.parents if len(p.select("h2"))==1 and
                           any(day(t) for t in p.stripped_strings)),None)
                if not card:raise ValueError("Ai2 Research 카드 날짜 확인 실패")
                yield urljoin(page,link["href"]),link.h2.get_text(" ",strip=True),next(day(t) for t in card.stripped_strings if day(t))
            following=next((a for a in soup.select("main a[href]") if a.get_text(strip=True)=="Next"),None)
            page=urljoin(page,following["href"]) if following else None
        return
    if s.get("adapter")=="openai_publications":
        from openai_publications import visible_index
        with requests.Session() as session:
            session.headers.update(HEADERS)
            yield from visible_index(s,session)
        return
    if s.get("adapter")=="sakana_research":
        from sakana_research import entries
        yield from entries(s)
        return
    if s.get("adapter")=="ibm_publications":
        from ibm_publication import catalog as ibm_catalog
        yield from ibm_catalog(s,fetch,day)
        return
    if s.get("adapter")=="nvidia_extra":
        from nvidia_extra import entries
        yield from entries(s)
        return
    if s.get("adapter")=="deepmind_publications":
        from deepmind_publications import publications
        yield from publications(s,fetch,day)
        return
    if s.get("adapter")=="strict_publications":
        from strict_publications import entries
        yield from entries(s)
        return
    if s.get("adapter")=="official_paper_sections":
        from official_paper_sections import section_catalog
        yield from section_catalog(s)
        return
    if s.get("adapter")=="lab_publications":
        from lab_publications import entries
        yield from entries(s)
        return
    if s.get("adapter")=="interactive_catalogs":
        from interactive_catalogs import entries
        yield from entries(s)
        return
    if s.get("adapter")=="bair_archive":
        from bair_archive import entries
        yield from entries(s)
        return
    if s.get("next_selector") or s.get("pages"):
        seen = set()
        page_url = s["url"]
        fixed = list(dict.fromkeys([s["url"],*s.get("pages",[])]))
        for page_number in range(4):
            if not page_url or page_url in seen:
                break
            if urlsplit(page_url).hostname != urlsplit(s["url"]).hostname:
                raise ValueError("목록의 다음 페이지가 다른 도메인을 가리킴")
            seen.add(page_url)
            response = fetch(page_url)
            soup = BeautifulSoup(response.content, "html.parser")
            s["found_on"]=response.url
            yield from catalog_page(s,response,soup)
            following = None
            if s.get("next_selector"):
                anchor = soup.select_one(s["next_selector"])
                if anchor and anchor.get("href"):
                    following = urljoin(response.url,anchor["href"])
            elif page_url in fixed and fixed.index(page_url)+1<len(fixed):
                following=fixed[fixed.index(page_url)+1]
            page_url=s.get("resume") if page_number==0 and s.get("resume") else following
            s["continue_at"]=page_url if page_url not in seen else None
        return
    if s.get("feed") and s["id"]=="1":
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
                if post.get("articleType")=="news":
                    continue
                path=post.get("linkedUrl")
                slug=(post.get("slug") or {}).get("current")
                if not path and slug and post.get("articleType") in ("research","engineering","institute"):
                    path=f"/{post['articleType']}/{slug}"
                if path and post.get("title") and keep_research("1",urljoin(s["url"],path),post["title"],post.get("summary") or ""):
                    yield urljoin(s["url"],path),post["title"].strip(),day(post.get("publishedOn") or "")
            if not data["hasNextPage"]:
                break
            page+=1
        return
    page = fetch(s["url"])
    yield from catalog_page(s,page,BeautifulSoup(page.content,"html.parser"))


def catalog_page(s,page,soup):
    if urlsplit(page.url).hostname.removeprefix("www.") != urlsplit(s["url"]).hostname.removeprefix("www."):
        raise ValueError("등록된 기관 도메인 밖으로 이동")
    if s.get("section")=="meta_publications":
        from meta_publications import cards
        yield from cards(soup,page.url,day)
        return
    if s["id"]=="31" and s["url"]==MILA_PUBLICATIONS:
        from mila_catalog import parse_cards,pick
        for card in parse_cards(soup):
            selected=pick(card)
            if selected:
                yield selected
        return
    for row in soup.select(s["row"]):
        link = row.select_one(s["link"]) if "link" in s else row
        if not link or not link.has_attr("href"):
            continue
        href = urljoin(page.url,link["href"])
        if urlsplit(href).scheme not in ("https","http") or href.rstrip("/")==page.url.rstrip("/"):
            continue
        if s["id"]=="23":
            labels={p.get_text(" ",strip=True) for p in row.select(".fidings_card-right p:not(.text-size-small)")}
            section=urlsplit(href).path.strip("/").split("/")[0]
            categories={"science":{"Evaluations","Interpretability","Science of Scheming"},
                        "monitoring":{"Research"},"governance":{"Papers & Reports"}}
            if not (labels & categories.get(section,set())):
                continue
        label = row if s.get("title")=="self" else row.select_one(s["title"]) if s.get("title") else (link.select_one("h2,h3,h4") or link)
        if not label:
            continue
        title = " ".join(label.stripped_strings)
        if s["id"]=="4" and title.lower()=="read the paper":
            title = urlsplit(href).path.rstrip("/").rsplit("/",1)[-1].replace("-"," ").capitalize()
        if (len(title)<5 and not (s["id"]=="20" and urlsplit(s["url"]).hostname=="pub.sakana.ai" and title)) or len(title)>400 or re.fullmatch(r"[\W\d]*(?:authors?|comments?|paper|pdf|read more|view all|publication|research|publications)[\W\d]*",title,re.I):
            continue
        date_tag = row.select_one(s["date"]) if s.get("date") else None
        published = day(date_tag.get_text(" ",strip=True)) if date_tag else None
        if s["id"]=="5":
            card=row.find_parent("article")
            stamp=card.select_one(".content-excerpt__journal-and-issue,.content-excerpt__published") if card else None
            if stamp:
                dates=re.findall(r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+(?:\d{1,2},\s+)?\d{4}",stamp.get_text(" ",strip=True))
                if dates:published=day(dates[-1])
        if s["id"]=="27":
            card=row.find_parent("div",class_="item")
            if card:
                published=next((date for text in card.stripped_strings if (date:=day(text))),None)
        yield href,title,published


def collect(s, old, previous_status):
    cursor = previous_status.get("next_url")
    previous_pages = previous_status.get("page_cursors",{})
    next_pages = {}
    rows = {}
    errors = []
    memberships = {}
    listed_by_url = {l["url"]:l for l in listings(s)}
    aliases=(json.loads((ROOT/"config/nvidia_robotics_aliases.json").read_text("utf8"))
             if s["id"]=="6" else {})
    origins = {}
    reconciled = None
    for listing in listings(s):
        scan = dict(listing,id=s["id"],resume=previous_pages.get(listing["url"]))
        try:
            count = 0
            for url,title,published in catalog(scan):
                if url in aliases:
                    ref=aliases[url]
                    canonical=ref["url"]
                    memberships.setdefault(canonical,{})[listing["team"]]=listing["url"]
                    if canonical not in rows and ref["listed_on"] in listed_by_url:
                        rows[canonical]=(title,published,ref["listed_on"])
                        origins[canonical]=ref["found_on"]
                    count+=1
                    continue
                if eligible_link(url,listing) and keep_research(s["id"],url,title):
                    if listing.get("team"):
                        memberships.setdefault(url,{})[listing["team"]]=listing["url"]
                    if url not in rows or (published and not rows[url][1]):
                        rows[url]=(title,published,listing["url"])
                        origins[url]=scan.get("found_on",listing["url"])
                    count += 1
            if not count:
                errors.append((listing.get("team")+" · " if listing.get("team") else "")+"공식 목록에서 연구 링크를 확인하지 못함")
        except (requests.RequestException, ValueError, ElementTree.ParseError) as exc:
            errors.append(listing["url"]+" · "+str(exc)[:180])
            scan["continue_at"]=scan.get("continue_at") or scan.get("resume")
        if scan.get("continue_at"):
            next_pages[listing["url"]]=scan["continue_at"]
        if scan.get("index_summary"):
            reconciled=(scan["index_summary"],{article_id(s["id"],u) for u in rows})
        if scan.get("paper_metadata"):
            s["paper_metadata"]=scan["paper_metadata"]
        if scan.get("labels"):
            s["labels"]=scan["labels"]
        if scan.get("publisher_total"):
            s["publisher_total"]=scan["publisher_total"]
        if scan.get("listing_order"):
            s["listing_order"]=scan["listing_order"]
        if scan.get("nonpapers"):
            s["nonpapers"]=scan["nonpapers"]
    verified = {}
    if s["id"] in ("10","13","15","24") and rows and not errors:
        s["current_members"]={article_id(s["id"],url) for url in rows}
    queue = []
    for url,(title,published,listing) in rows.items():
        key = article_id(s["id"],url)
        previous = old.get(key,{})
        if url in s.get("paper_metadata",{}):
            verified[url]=(title,published,listing,url)
        elif (listed_by_url[listing].get("adapter")=="openai_publications"
              or paper_target(url,listed_by_url[listing])):
            # The publisher's own paper card is the evidence for the outbound link.
            verified[url]=(title,published,listing,url)
        elif previous.get("listed_on")==listing and not obsolete_url(previous) and (
                previous.get("official_html") and not listed_by_url[listing].get("papers_only")
                or previous.get("academic_paper") and paper_target(previous["url"],listed_by_url[listing])):
            verified[url]=(title,published,listing,previous["url"])
        else:
            queue.append((url,title,published,listing))
    # Bound requests per institution. Future sweeps continue through the backlog.
    with ThreadPoolExecutor(max_workers=3) as checks:
        start = next((i for i,r in enumerate(queue) if r[0]==cursor),0)
        pending = queue[start:]+queue[:start]
        batch = pending if s["id"] in ("1","2") else pending[:120]
        for row,destination in zip(batch,checks.map(lambda r:verify_destination(r[0],listed_by_url[r[3]]),batch)):
            if destination:
                url,title,published,listing=row
                verified[url]=(title,published,listing,destination)
    more = len(batch)<len(queue)-start
    if more:
        next_pages=previous_pages
    return s,verified," / ".join(errors),pending[len(batch)][0] if more else None,memberships,next_pages,origins,reconciled


def listings(s):
    return s["additional"] if s["id"]=="1" else [s]+s.get("additional",[])


def obsolete_url(item):
    url=urlsplit(item["url"])
    if item["source"]=="0":return False
    if item["url"].rstrip("/") in REVIEWED_URLS or (item["source"],url.path.rstrip("/")) in REVIEWED:
        return True
    return item.get("source")=="14" and (
        item.get("collection")!="research_archive"
        or url.hostname=="qwen.ai" and url.path.startswith("/research/"))


def destination_key(source,url):
    parsed=urlsplit(url)
    host=parsed.hostname.removeprefix("www.")
    path=parsed.path.rstrip("/")
    if host=="openreview.net" and openreview_id(url):
        return source,"openreview",openreview_id(url)
    if host=="arxiv.org":
        paper=re.fullmatch(r"/(?:abs|pdf|html)/([\w./-]+?)(?:v\d+)?(?:\.pdf)?",path)
        if paper:return source,"arxiv",paper[1]
    if host in ("doi.org","dx.doi.org"):
        return source,"doi",path.lower()
    if host=="semanticscholar.org":
        paper=re.fullmatch(r"/paper/(?:[^/]+/)?([a-fA-F0-9]{40})",path)
        if paper:return source,"semanticscholar",paper[1].lower()
    query=urlencode([(k,v) for k,v in parse_qsl(parsed.query,keep_blank_values=True)
                     if not k.startswith("utm_") and k not in ("view_from","bc")])
    if parsed.fragment.startswith(":~:text="):
        return source,host,path,query,parsed.fragment
    return source,host,path,query


def unique_destinations(items):
    unique={}
    for item in items.values():
        key=destination_key(item["source"],item["url"])
        if key not in unique:
            unique[key]=item
        else:
            first=unique[key]
            first["discovered"]=min(first["discovered"],item["discovered"])
            if not first.get("published") and item.get("published"):
                first["published"]=item["published"]
                first["date_basis"]=item.get("date_basis")
            if item.get("teams"):
                first.setdefault("teams",{}).update(item["teams"])
    return unique.values()


def main():
    sources = json.loads((ROOT/"config/sources.json").read_text("utf8"))
    output = ROOT/"docs/data.json"
    snapshot = catalog_snapshot.read(output)
    old = {x["id"]:x for x in snapshot["items"]}
    lists = {s["id"]:{v["url"] for v in listings(s)} for s in sources}
    policies={s["id"]:{v["url"]:v for v in listings(s)} for s in sources}
    # Retain historical records only under a still-configured, qualifying listing.
    items={}
    for key,item in old.items():
        listing=policies.get(item["source"],{}).get(item.get("listed_on"))
        if not listing or obsolete_url(item) or (listing.get("scope_key") and item.get("scope_key")!=listing["scope_key"]):
            continue
        if not keep_research(item["source"],item["url"],item["title"]):
            continue
        if ((item.get("academic_paper") or item.get("openreview")) and paper_target(item["url"],listing)
                or item.get("official_html") and not listing.get("papers_only") and official_post(item["url"],listing["url"])):
            items[key]=item
    for item in items.values():
        if "teams" in item:
            item["teams"]={team:page for team,page in item["teams"].items() if page in lists[item["source"]]}
            if not item["teams"]:
                del item["teams"]
    status = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        for s, rows, error, cursor, memberships, pages, origins, reconciled in pool.map(lambda s:collect(s,old,snapshot["status"].get(s["id"],{})),sources):
            current=reconciled[1] if reconciled else s.get("current_members")
            if current is not None:
                for key in [k for k,x in items.items() if x["source"]==s["id"] and k not in current]:
                    del items[key]
            for excluded in s.get("nonpapers",()):
                items.pop(article_id(s["id"],excluded),None)
            for url,(title,published,listing,destination) in rows.items():
                key = article_id(s["id"],url)
                previous = old.get(key,{})
                items[key] = dict(previous,id=key,source=s["id"],url=destination,title=title,discovered=previous.get("discovered",NOW),
                                  listing_date=published or previous.get("listing_date"),published=previous.get("published"),listed_on=listing,found_on=origins[url],official_html=True,kind="공식 연구 게시글")
                items[key].pop("openreview",None)
                items[key].pop("academic_paper",None)
                if policies[s["id"]][listing].get("scope_key"):
                    items[key]["scope_key"]=policies[s["id"]][listing]["scope_key"]
                if s["id"]=="14":
                    items[key]["collection"]="research_archive"
                if url in s.get("labels",{}):items[key]["index_label"]=s["labels"][url]
                if url in s.get("listing_order",{}):
                    items[key].update(catalog_order=s["listing_order"][url],published=published,
                                      date_basis="공식 목록" if published else None)
                if url in s.get("paper_metadata",{}):
                    kind,venue=s["paper_metadata"][url]
                    items[key].update(publication_type=kind,venue=venue,ibm_verified=True)
                if paper_target(destination,policies[s["id"]][listing]):
                    items[key].update(academic_paper=True,openreview=bool(openreview_id(destination)),official_html=False,kind=policies[s["id"]][listing].get("paper_section","공식 논문 목록"),
                                      published=published,date_basis="공식 목록" if published else None)
                    if urlsplit(destination).fragment.startswith(":~:text="):
                        items[key]["kind"]="공식 목록 수록 연구"
                if url in memberships:
                    previous_teams={team:page for team,page in previous.get("teams",{}).items() if page in lists[s["id"]]}
                    items[key]["teams"]={**previous_teams,**memberships[url]}
            status[s["id"]] = dict(ok=bool(rows),count=len(rows),partial=bool(rows and error),error=error or "",next_url=cursor,page_cursors=pages)
            if s["id"]=="0":
                status["0"]["publisher_total"]=s.get("publisher_total") or snapshot["status"].get("0",{}).get("publisher_total")
            if reconciled:
                status[s["id"]]["index_summary"]=reconciled[0]
            elif s["id"]=="2":
                previous_status=snapshot["status"].get("2",{})
                status["2"]["last_verified_summary"]=previous_status.get("index_summary") or previous_status.get("last_verified_summary")
            print(s["name"],len(rows),error or "",flush=True)
    pending_ibm=[item for item in items.values() if item["source"]=="8" and not item.get("ibm_verified")]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for item,verified in zip(pending_ibm,pool.map(verify_ibm_item,pending_ibm)):
            if not verified:
                items.pop(item["id"],None)
                if verified is None:
                    status["8"].update(partial=True,error="일부 IBM 출판물의 상세 유형 확인 실패")
    articles=unique_destinations(items)
    retry_before=(datetime.fromisoformat(NOW)-timedelta(days=7)).date().isoformat()
    for item in articles:
        if item.get("date_basis")!="상세 글" and item.get("listing_date"):
            item.update(published=item["listing_date"],date_basis="공식 목록")
    pending=[item for item in articles if item["source"]!="15" and not (item.get("catalog_audited") and item.get("published")) and item.get("date_basis")!="상세 글" and not item.get("openreview") and not item.get("academic_paper")
             and item.get("date_checked","")<=retry_before]
    pending=sorted(pending,key=lambda item:item.get("date_checked",""))[:240]
    with ThreadPoolExecutor(max_workers=6) as pool:
        for item,date in zip(pending,pool.map(lookup_date,pending)):
            item["published"]=date or item.get("listing_date")
            item["date_basis"]="상세 글" if date else "공식 목록" if item["published"] else None
            item["date_checked"]=NOW[:10]
    ordered = sorted(articles,key=lambda x:x["published"] or "",reverse=True)
    catalog_snapshot.write(output,NOW,ordered,status)


if __name__=="__main__":
    main()

