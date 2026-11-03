"""Official publication catalogs for the strict Research/Publication sources."""
import re
from datetime import datetime
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup


def fetch(url, **params):
    response=requests.get(url,params=params,headers={"User-Agent":"AIResearchRadar/1.0 (https://github.com/leeklim/ai-research-radar)"},timeout=15)
    response.raise_for_status()
    return response


def entries(source):
    ident=source["id"]
    if ident=="29":
        # CSAIL's own Publications page identifies this specific DSpace community.
        # Scope on the server, never query by words in a paper's title or affiliation.
        community="a099ca0a-5497-44fb-9fd4-6900bf7e205b"
        page=int(source.get("resume") or 1)
        for number in (0,page,page+1):
            result=fetch("https://dspace.mit.edu/server/api/discover/search/objects",scope=community,dsoType="item",
                         sort="dc.date.issued,DESC",page=number,size=50).json()["_embedded"]["searchResult"]
            for obj in result["_embedded"].get("objects",[]):
                item=obj["_embedded"]["indexableObject"]
                if not re.fullmatch(r"1721\.1/\d+",item.get("handle","")):
                    continue
                dates=item["metadata"].get("dc.date.issued",[])
                date=dates[0]["value"] if dates else None
                yield "https://dspace.mit.edu/handle/"+item["handle"],item["name"],date if date and re.fullmatch(r"\d{4}(?:-\d{2}(?:-\d{2})?)?",date) else None
            if number+1>=result["page"]["totalPages"]:
                source["continue_at"]=1
                break
            source["continue_at"]=number+1
        return

    soup=BeautifulSoup(fetch(source["url"]).content,"html.parser")
    if ident=="22":
        # Featured in-house result pages and citations explicitly labeled Paper,
        # not unrelated links in the research writeups.
        for card in soup.select('main a[href]:has(h3)'):
            title=card.select_one('h3').get_text(" ",strip=True)
            yield urljoin(source["url"],card["href"]),title,None
        for row in soup.select("main article"):
            title=row.select_one("h3")
            if not title:continue
            for a in row.select("a[href]"):
                if a.get_text(" ",strip=True).lower()=="paper":
                    yield urljoin(source["url"],a["href"]),title.get_text(" ",strip=True),None
    elif ident=="24":
        for group in soup.select(".library-year-group"):
            year=group.select_one("h2")
            date=year.get_text(" ",strip=True) if year else ""
            for card in group.select("a.library-entry[href]"):
                label=card.select_one("h3")
                if label:yield urljoin(source["url"],card["href"]),label.get_text(" ",strip=True),date if re.fullmatch(r"\d{4}",date) else None
    elif ident=="25":
        for card in soup.select('a[href^="/papers/"]:has(h4)'):
            title=card.h4.get_text(" ",strip=True)
            match=re.search(r"\bPublished\s+([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})",card.get_text(" ",strip=True))
            date=None
            if match:
                for fmt in ("%b %d, %Y","%B %d, %Y"):
                    try:date=datetime.strptime(match[1],fmt).date().isoformat();break
                    except ValueError:pass
            yield urljoin(source["url"],card["href"]),title,date
    elif ident=="27":
        for row in soup.select("div.item.row"):
            a=row.select_one("h4 a[href]")
            if not a:continue
            label=row.select_one(".meta")
            year=re.search(r"\b(19\d\d|20\d\d)\b",label.get_text(" ",strip=True)) if label else None
            if not year:
                h=row.find_previous("h2")
                year=re.fullmatch(r"(\d{4})", h.get_text(strip=True)) if h else None
            yield urljoin(source["url"],a["href"]),a.get_text(" ",strip=True),year[1] if year else None
    elif ident=="30":
        for p in soup.select("p"):
            by_href={}
            for a in p.select('a[href]'):
                if ".pdf" in a["href"].lower() and a.get_text(strip=True):
                    by_href.setdefault(a["href"],[]).append(a)
            for href,anchors in by_href.items():
                # Some titles are split across adjacent links to the very same PDF.
                parts=[a.get_text(" ",strip=True) for a in anchors]
                title=" ".join(parts)
                title=re.sub(r"\b([A-Z]) ([a-z]+)\b",r"\1\2",title) if len(parts)>1 else title
                # Author/year follows the title within the same dissertation entry.
                siblings=[]
                for node in anchors[-1].next_siblings:
                    if getattr(node,"name",None)=="a" and node.get_text(strip=True):
                        break
                    siblings.append(node.get_text(" ",strip=True) if getattr(node,"name",None) else str(node))
                match=re.search(r"\b(19\d\d|20\d\d)\b"," ".join(siblings))
                if not match and len(by_href)==1:
                    years=re.findall(r"\b(?:19|20)\d\d\b",p.get_text(" ",strip=True))
                    year=years[-1] if years else None
                else:
                    year=match[1] if match else None
                yield urljoin(source["url"],href),title,year
