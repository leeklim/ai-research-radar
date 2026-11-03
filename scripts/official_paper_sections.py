"""Collectors for the named paper sections of official research pages."""
import json
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup


def get(url, **params):
    response=requests.get(url, headers={"User-Agent":"AIResearchRadar/1.0 (https://github.com/leeklim/ai-research-radar)"},
                          params=params or None, timeout=18)
    response.raise_for_status()
    if not response.content:
        raise ValueError("공식 연구 페이지가 빈 응답을 반환함")
    return response


def deepseek(url):
    soup=BeautifulSoup(get(url).content,"html.parser")
    heading=next((h for h in soup.select("section > h2")
                  if h.get_text(" ",strip=True) in ("Research Index","Research Papers")),None)
    if heading is None:
        raise ValueError("DeepSeek의 Research Index 섹션을 확인하지 못함")
    first_page={}
    for a in heading.parent.select("a.ds-research-item[href]"):
        title=a.select_one(".ds-research-title")
        stamp=a.select_one(".ds-research-date")
        if title and stamp:
            date=datetime.strptime(stamp.get_text(strip=True),"%B %d, %Y").date().isoformat()
            first_page[a["href"]]=(title.get_text(" ",strip=True),date)
    if not first_page:
        raise ValueError("DeepSeek 연구 목록에 논문 카드가 없음")
    for href,(title,date) in first_page.items():
        yield href,title,date
    if not heading.parent.find("button"):
        return
    # View All renders the remaining rows from the component's own article array.
    # Match it to the visible first page before trusting any supplemental records.
    js_string=r'"(?:\\.|[^"\\])*"'
    row=re.compile(r'\{date:('+js_string+r'),title:('+js_string+r'),href:('+js_string+r')\}')
    for tag in soup.select("script[src]"):
        src=urljoin(url,tag["src"])
        if urlsplit(src).hostname != urlsplit(url).hostname or not re.search(r'/news/page-[^/]+\.js$',urlsplit(src).path):
            continue
        expanded={}
        for date,title,href in row.findall(get(src).content.decode("utf8")):
            date,title,href=map(json.loads,(date,title,href))
            if re.fullmatch(r"\d{4}-\d{2}(?:-\d{2})?",date):
                if href in first_page and first_page[href][0]==title and first_page[href][1].startswith(date):
                    date=first_page[href][1]
                expanded[href]=(title,date)
        if len(expanded)>len(first_page) and all(expanded.get(link)==value for link,value in first_page.items()):
            for href,(title,date) in expanded.items():
                if href not in first_page:
                    yield href,title,date
            return
    raise ValueError("DeepSeek 더보기 목록을 공식 화면과 대조하지 못함")


def qwen(url):
    # These are the two card collections used by the scrollable Research Index.
    legacy=get("https://qwen.ai/api/page_config",code="research.research-list",language="en").json()
    current=get("https://qwen.ai/api/v2/article/retrieval",type="qwen_ai",language="en-US").json()["data"]["articles"]
    cards={p["id"]:(p.get("title"),p.get("date"),p.get("tags",[])) for p in legacy if p.get("id")}
    for p in current:
        extra=p.get("extra") or {}
        cards[p["path"]]=(p.get("title"),extra.get("date"),extra.get("tags",[]))
    for slug,(title,raw,tags) in cards.items():
        if "Research" not in tags or not re.fullmatch(r"[\w.-]+",slug) or not title:
            continue
        stamp=datetime.fromisoformat(raw.replace("Z","+00:00")) if raw else None
        date=stamp.astimezone(timezone(timedelta(hours=9))).date().isoformat() if stamp and stamp.tzinfo else (raw or "")[:10] or None
        yield urljoin(url,"/blog?"+urlencode({"id":slug})),title.strip(),date


def section_catalog(s):
    url=s["url"]
    if s["id"]=="12":
        yield from deepseek(url)
    elif s["id"]=="14":
        yield from qwen(url)
    elif s["id"]=="13":
        soup=BeautifulSoup(get(url).content,"html.parser")
        # All cards revealed by the button are already in this component's DOM.
        sections=[block for block in soup.select("mistral-section-posts")
                  if (heading:=block.find_previous(["h1","h2","h3"]))
                  and heading.get_text(" ",strip=True).rstrip(".").casefold()=="publications"]
        if len(sections)!=1:
            raise ValueError("Mistral Publications 섹션을 확인하지 못함")
        cards=sections[0].select("a.js-listing-item[href]")
        counter=re.search(r"\b(\d+) results?\b",sections[0].get_text(" ",strip=True),re.I)
        if not cards or not counter or len(cards)!=int(counter[1]):
            raise ValueError("Mistral Publications 표기 건수와 카드 수 불일치")
        for a in cards:
            title=a.select_one("p.text-h5")
            if title:
                yield urljoin(url,a["href"]),title.get_text(" ",strip=True),None
    elif s["id"]=="19":
        soup=BeautifulSoup(get(url).content,"html.parser")
        for row in soup.select("main li"):
            title=row.select_one("span.font-serif")
            link=next((a for a in row.select("a[href]") if a.get_text(" ",strip=True).lower()=="view publication"),None)
            if title and link:
                tag=row.select_one("time")
                date=datetime.strptime(tag.get_text(strip=True),"%m.%d.%Y").date().isoformat() if tag else None
                yield urljoin(url,link["href"]),title.get_text(" ",strip=True),date
