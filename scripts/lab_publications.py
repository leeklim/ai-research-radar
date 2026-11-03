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

    def is_paper(url):
        dest = urlsplit(url)
        pattern=s.get("paper_links",{}).get(dest.hostname)
        return dest.scheme=="https" and bool(pattern and re.fullmatch(pattern,dest.path))

    if s["lab_data"]=="fair":
        soup=BeautifulSoup(fetch(s["url"]).content,"html.parser")
        for a in soup.select("a[href]"):
            url=urljoin(s["url"],a["href"])
            if urlsplit(url).hostname=="ai.meta.com" and "/research/publications/" in urlsplit(url).path:
                yield url,urlsplit(url).path.rstrip("/").rsplit("/",1)[-1].replace("-"," ").capitalize(),None
            elif is_paper(url) and a.get_text(" ",strip=True).casefold() in ("read the paper","research paper","read the technical report"):
                # The roundup sometimes reuses a section header for several
                # different PDFs. Read the cited paper title, not a nearby heading.
                paper_id=urlsplit(url).path.rstrip("/").rsplit("/",1)[-1].removesuffix(".pdf")
                try:
                    paper=BeautifulSoup(fetch("https://arxiv.org/abs/"+paper_id).content,"html.parser")
                except requests.RequestException:
                    continue
                heading=paper.select_one("meta[name=citation_title]")
                if heading and heading.get("content"):
                    yield url,heading["content"].strip(),None
        return
    if s["lab_data"]=="nvidia_cards":
        soup=BeautifulSoup(fetch(s["url"]).content,"html.parser")
        seen=set()
        for a in soup.select(s["row"]):
            href=urljoin(s["url"],a["href"])
            title=a.get_text(" ",strip=True)
            if not title or href in seen:
                continue
            seen.add(href)
            card=a.find_parent(class_="stream-item") or a.find_parent(class_="card-simple") or a.find_parent("article")
            paper=None
            if card:
                for link in card.select("a[href]"):
                    target=urljoin(s["url"],link["href"])
                    if link.get_text(" ",strip=True).casefold() in ("paper","pdf","arxiv","arxiv pdf") and is_paper(target):
                        paper=target
                        break
            yield paper or href,title,None
        return
    if s["lab_data"]=="cosmos":
        data=fetch(urljoin(s["url"],"data/publications.json")).json()
        cards=[]
        for p in data.values():
            paper=next((urljoin(s["url"],a["url"]) for a in p["links"]
                        if a["label"].casefold()=="paper" and is_paper(urljoin(s["url"],a["url"]))),None)
            project=next((a["url"] for a in p["links"] if a["label"].casefold()=="project"),None)
            if paper or project:
                cards.append((p["title"],paper or project))
    else:
        if s["lab_data"]=="sil":
            html=BeautifulSoup(fetch(urljoin(s["url"],"main.html")).content,"html.parser")
            script_node=html.select_one("script[src$='/publications.js']")
            title_field,link_field,paper_field='"title"','"project"','"paper"'
        else:
            html=BeautifulSoup(fetch(s["url"]).content,"html.parser")
            script_node=html.select_one('script[src*="/pages/publications-"]')
            title_field,link_field,paper_field="title","projectLink","paperLink"
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
            paper=re.search(r'(?:^|[,{])\s*'+re.escape(paper_field)+r'\s*:\s*'+string,obj[0])
            original=json.loads(paper[1]) if paper else None
            if title and original and is_paper(urljoin(s["url"],original)):
                rows.append((json.loads(title[1]),original))
            elif title and link:
                rows.append((json.loads(title[1]),json.loads(link[1])))
        cards=rows
    for title,href in cards:
        if not href or href.startswith(("#","?")):
            continue
        url=urljoin(s["url"],href)
        if is_paper(url) or (urlsplit(url).hostname=="research.nvidia.com" and not urlsplit(url).path.lower().endswith(".pdf")):
            yield url,title,None
