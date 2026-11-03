"""Explicit publication sections linked by NVIDIA's institutional lab directory."""
import re
from datetime import datetime
from urllib.parse import urljoin,urlsplit

import requests
from bs4 import BeautifulSoup

UA={"User-Agent":"AIResearchRadar/1.0 (https://github.com/leeklim/ai-research-radar)"}


def fetch(url):
    r=requests.get(url,headers=UA,timeout=15)
    r.raise_for_status()
    return r


def text(node):
    return node.get_text(" ",strip=True) if node else ""


def date(node):
    value=text(node)
    for fmt in ("%Y-%m-%d","%B %d, %Y","%b %d, %Y","%B, %Y","%B %Y","%b %Y","%Y"):
        try:
            obj=datetime.strptime(value,fmt)
            return obj.strftime("%Y") if fmt=="%Y" else obj.strftime("%Y-%m") if "%d" not in fmt else obj.date().isoformat()
        except ValueError:continue
    return None


def useful(href):
    u=urlsplit(href)
    if u.scheme not in ("http","https") or not u.hostname:return False
    if u.path.strip("/"):return True
    # A paper's named, project-specific site may itself be a root URL. Do
    # not admit root URLs of general publishers, aggregators, or hosting hubs.
    return u.hostname.endswith(".github.io") or u.hostname in ("www.pytorchfi.dev","rfd4-proteina.org")


def original(card,page,primary,section):
    links=card.select("a[href]")
    for name in ("arxiv","arxiv pdf","paper","pdf","publication"):
        for a in links:
            candidate=urljoin(page,a["href"])
            if candidate=="https://openreview.net/forum?id=TscdNx8udf5https://github.com/smpl-env/smpl":
                # This specific Robotics card concatenates the paper and code
                # URLs. The authors' SMPL documentation confirms the forum ID.
                candidate="https://openreview.net/forum?id=TscdNx8udf5"
            if text(a).casefold()==name and useful(candidate):
                return candidate
    if section=="srl":
        for a in links:
            href=urljoin(page,a["href"])
            if text(a).casefold() in ("website","project","project page") and useful(href):
                return href
    return urljoin(page,primary["href"]) if primary and primary.has_attr("href") else None


def entries(s):
    page=s["url"];kind=s["nv_section"]
    if kind=="digital-biology":
        # The lab's own script.js loads content.json and applies this type filter.
        for card in fetch(urljoin(page,"content.json")).json():
            if card.get("type")=="Papers" and card.get("link") and card.get("title"):
                yield urljoin(page,card["link"]),card["title"],card.get("date")
        return
    soup=BeautifulSoup(fetch(page).content,"html.parser")
    if kind=="nemotron":
        by_url={}
        for a in soup.select("article a[href$='.pdf']"):
            href=urljoin(page,a["href"])
            if "/labs/nemotron/files/" in href and text(a):
                if len(text(a))>len(by_url.get(href,"")):by_url[href]=text(a)
        for href,title in by_url.items():yield href,title,None
        return
    if kind=="conversation":
        base=page
        seen=set();todo={1:base}
        while todo:
            number=min(todo);page=todo.pop(number)
            if page in seen:continue
            seen.add(page);s["found_on"]=page
            if page!=base:soup=BeautifulSoup(fetch(page).content,"html.parser")
            for card in soup.select("article.md-post"):
                a=card.select_one("h2 a[href^='http']") or card.select_one("h2 a[href]")
                if a:
                    yield urljoin(page,a["href"]),text(card.select_one('h2')),date(card.select_one("time"))
            for a in soup.select("a.md-pagination__link[href]"):
                link=urljoin(page,a["href"]);num=text(a)
                if num.isdigit() and link.startswith(base) and link not in seen:todo[int(num)]=link
        return
    if kind=="hpx":
        for c in soup.select("#publications [id^='publications-'] > .nv-accordion-content"):
            h=c.select_one(".nv-text--title-sm")
            a=h.select_one("a[href]") if h else None
            # The title is the lab's chosen destination. If it is not a link, only
            # use a paper link explicitly displayed for the same named card.
            a=a or next((n for n in c.select(".links-section a[href]") if re.search(r"publication|\.pdf|paper version|arxiv",text(n),re.I)),None)
            if a and h:
                heading=c.parent.get("id","")
                match=re.fullmatch(r"publications-(\d{4})",heading)
                yield urljoin(page,a["href"]),text(h),match[1] if match else None
        return
    cards={
        "lpr":"article.lpr-paper","aie":"article.publication-card",
        "srl":".card-simple","eai":".pub-list-item",
    }
    for c in soup.select(cards[kind]):
        if kind=="lpr":
            title=c.select_one("h2");primary=c.select_one("a.lpr-paper-primary[href]")
        elif kind=="aie":
            title=c.select_one("h3");primary=c.select_one("h3 a[href]")
        elif kind=="srl":
            title=c.select_one(".article-title");primary=c.select_one(".article-title a[href]")
        else:
            title=c.select_one(":scope > a[href]");primary=title
        if not text(title):continue
        href=original(c,page,primary,kind)
        if href and useful(href):
            when=date(c.select_one(".article-date,time"))
            if not when:
                venue=text(c.select_one(".publication-venue,.lpr-paper-venue"))
                match=re.search(r"(?:·|\|)\s*((?:19|20)\d{2})\s*$",venue)
                when=match[1] if match else None
            if not when and kind=="eai":
                match=re.search(r"\(((?:19|20)\d{2})\)\.",c.get_text(" ",strip=True))
                when=match[1] if match else None
            yield href,text(title),when
