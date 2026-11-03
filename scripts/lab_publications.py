"""Read NVIDIA lab publication cards from the same assets used by their public pages."""
import json
import re
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup


def entries(s):
    def fetch(url):
        response=requests.get(url,headers={"User-Agent":"AIResearchRadar/1.0 (https://github.com/leeklim/ai-research-radar)"},timeout=15)
        response.raise_for_status()
        return response

    if s["lab_data"]=="ai2":
        soup=BeautifulSoup(fetch(s["url"]).content,"html.parser")
        urls={urljoin(s["url"],a["href"]) for a in soup.select("main a[href*='/blog/'],main a[href*='/papers/']")}
        for url in sorted(urls):
            if urlsplit(url).hostname not in ("allenai.org","www.allenai.org"):
                continue
            response=fetch(url)
            if urlsplit(response.url).hostname not in ("allenai.org","www.allenai.org") or "text/html" not in response.headers.get("Content-Type","").lower():
                continue
            heading=BeautifulSoup(response.content,"html.parser").select_one("main h1")
            if heading:
                yield url,heading.get_text(" ",strip=True),None
        return
    if s["lab_data"]=="fair":
        soup=BeautifulSoup(fetch(s["url"]).content,"html.parser")
        for a in soup.select("a[href*='/research/publications/']"):
            url=urljoin(s["url"],a["href"])
            if urlsplit(url).hostname=="ai.meta.com":
                yield url,urlsplit(url).path.rstrip("/").rsplit("/",1)[-1].replace("-"," ").capitalize(),None
        return
    if s["lab_data"]=="cosmos":
        data=fetch(urljoin(s["url"],"data/publications.json")).json()
        cards=((p["title"],link["url"]) for p in data.values() for link in p["links"]
               if link["label"].casefold()=="project")
    else:
        if s["lab_data"]=="sil":
            html=BeautifulSoup(fetch(urljoin(s["url"],"main.html")).content,"html.parser")
            script_node=html.select_one("script[src$='/publications.js']")
            title_field,link_field='"title"','"project"'
        else:
            html=BeautifulSoup(fetch(s["url"]).content,"html.parser")
            script_node=html.select_one('script[src*="/pages/publications-"]')
            title_field,link_field="title","projectLink"
        if not script_node or not script_node.get("src"):
            raise ValueError("NVIDIA 공식 연구 목록에서 게시글 데이터 스크립트를 확인하지 못함")
        raw=fetch(urljoin(s["url"],script_node["src"])).text
        # Both assets render cards from flat objects. Parse the two string fields;
        # never evaluate remote JavaScript or extract links from unrelated objects.
        string=r'("(?:[^"\\]|\\.)*")'
        rows=[]
        for obj in re.finditer(r'\{(?:[^{}"\']|"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\')*\}',raw):
            title=re.search(r'(?:^|[,{])\s*'+re.escape(title_field)+r'\s*:\s*'+string,obj[0])
            link=re.search(r'(?:^|[,{])\s*'+re.escape(link_field)+r'\s*:\s*'+string,obj[0])
            if title and link:
                rows.append((json.loads(title[1]),json.loads(link[1])))
        cards=rows
    for title,href in cards:
        if not href or href.startswith(("#","?")):
            continue
        url=urljoin(s["url"],href)
        if urlsplit(url).hostname=="research.nvidia.com" and not urlsplit(url).path.lower().endswith(".pdf"):
            yield url,title,None
