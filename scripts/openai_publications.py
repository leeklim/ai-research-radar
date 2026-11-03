import json
import re
import requests
from datetime import datetime
from urllib.parse import urljoin,urlsplit
from xml.etree import ElementTree as ET
from bs4 import BeautifulSoup

TARGET='/research/index/publication'
MONTH='January|February|March|April|May|June|July|August|September|October|November|December'


def component_data(soup):
    chunks=[]
    for script in soup.select("script"):
        text=(script.string or "").strip().rstrip(";")
        if text.startswith("self.__next_f.push(") and text.endswith(")"):
            message=json.loads(text[len("self.__next_f.push("):-1])
            if len(message)>1 and isinstance(message[1],str):chunks.append(message[1])
    return "".join(chunks)


def openai_publication_candidates(session):
    seen=set()
    for topic in ('publication','research'):
        address=f'https://openai.com/sitemap.xml/{topic}/'
        response=session.get(address,timeout=25);response.raise_for_status()
        for node in ET.fromstring(response.content).findall('{*}url/{*}loc'):
            url=node.text or ''
            if urlsplit(url).hostname=='openai.com' and url not in seen:
                seen.add(url);yield url

def verified_openai_article(session,url):
    response=session.get(url,timeout=15);response.raise_for_status()
    doc=BeautifulSoup(response.content,'html.parser')
    stream=component_data(doc)
    slug=urlsplit(url).path.strip("/")
    for match in re.finditer(r'\{(?="(?:id|slug|title|__typename|pageType|publicationDate)")',stream):
        try:record=json.JSONDecoder().raw_decode(stream,match.start())[0]
        except ValueError:continue
        if (record.get("slug")!=slug or record.get("pageType")!="Article" or not record.get("title")
                or not any(isinstance(tag,dict) and tag.get("slug")=="publication" for tag in record.get("categories") or [])):
            continue
        return dict(url=url,title=record["title"],published=(record.get("publicationDate") or "")[:10] or None,
                    found_on=response.url)
    h=doc.select_one('main h1,article h1')
    if not h:return None
    for container in list(h.parents)[:6]:
        if container.name in ('body','html') or container.select_one('nav'):break
        for link in container.select('a[href]'):
            official=urljoin(response.url,link['href'])
            if (urlsplit(official).hostname!='openai.com' or
                urlsplit(official).path.rstrip('/')!=TARGET or
                link.get_text(' ',strip=True).lower()!='publication'):
                continue
            raw=next((m[0] for t in container.stripped_strings if (m:=re.search(r'\b(?:'+MONTH+r') \d{1,2}, \d{4}\b',t))),None)
            return dict(source='0',url=response.url,title=h.get_text(' ',strip=True),
                        published=datetime.strptime(raw,'%B %d, %Y').strftime('%Y-%m-%d') if raw else None,
                        listed_on=official,found_on=response.url,publisher_kind='Publication')
    return None


def visible_index(s,session):
    """Read the Publication component itself, including cards with external URLs."""
    for url in (s["url"],"https://openai.com/ko-KR/research/index/publication/","https://openai.com/ja-JP/research/index/publication/"):
        try:
            response=session.get(url,timeout=15)
            response.raise_for_status()
        except requests.RequestException:
            continue
        soup=BeautifulSoup(response.content,"html.parser")
        stream=component_data(soup)
        for match in re.finditer(r'\{"dynamicPageLists":',stream):
            props=json.JSONDecoder().raw_decode(stream[match.start():])[0]
            for index,group in zip(props["dynamicPageLists"],props["children"][3]["initialResults"]):
                if index.get("tabId")!="publication" or index.get("pageQueries")!=[{"pageTypes":["Article"],"categories":["publication"]}]:
                    continue
                s["publisher_total"]=group["total"]
                for card in group["items"]:
                    target=card.get("externalUrl") or urljoin("https://openai.com/",card["slug"].strip("/")+"/")
                    labels=card.get("categories") or []
                    if labels:s.setdefault("labels",{})[target]=labels[0]["slug"].capitalize()
                    yield target,card["title"],(card.get("publicationDate") or "")[:10] or None
                return
