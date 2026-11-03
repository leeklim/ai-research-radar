"""First-party newsroom feeds whose pagination is handled in client-side code."""
import re
from functools import lru_cache
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup


def _get(url, missing_ok=False, **params):
    response = requests.get(url, params=params, timeout=15, headers={"User-Agent": "AIResearchRadar/1.0 (https://github.com/leeklim/ai-research-radar)"})
    # Don't log the query string; Jina's Ghost Content API includes its public read key.
    if response.status_code==404 and missing_ok:
        return None
    if not response.ok:
        raise ValueError(f"HTTP {response.status_code}: {urlsplit(url).hostname}")
    return response


def _jina(source):
    # Follow the same newsroom store loaded by the public application. Its published
    # Ghost Content key is read from the application's current asset, never hardcoded.
    home = BeautifulSoup(_get(source["url"]).content,"html.parser")
    entry = home.select_one('script[type=module][src*="/assets/index-"]')
    if not entry:
        raise ValueError("Jina newsroom application entry not found")
    entry_url = urljoin(source["url"],entry["src"])
    store = re.search(r'assets/(blogs-[A-Za-z0-9_-]+\.js)', _get(entry_url).text)
    if not store:
        raise ValueError("Jina newsroom store not found")
    key = re.search(r'(?:key:"|[?&]key=)([0-9a-f]{26})', _get(urljoin(entry_url,store[1])).text)
    if not key:
        raise ValueError("Jina public newsroom content endpoint unavailable")
    payload = _get("https://cms.jina.ai/ghost/api/content/posts/",key=key[1], limit="all", include="tags", fields="slug,title,published_at").json()
    for post in payload["posts"]:
        slug = post["slug"]
        tags = {t["slug"] for t in post.get("tags",[])}
        if "tech-blog" not in tags and not ("press" in tags and re.match(r"jina-(?:embeddings|reranker|code|vlm|clip|reader|ocr|colbert|segmenter)",slug)):
            continue
        if re.fullmatch(r"[\w-]+",slug):
            yield urljoin(source["url"],slug+"/"),post["title"],(post.get("published_at") or "")[:10] or None


def _mit(source):
    # The official news Angular application uses 24-row offsets. Limit archive
    # bandwidth per refresh while revisiting the newest filtered results each run.
    endpoint = urljoin(source["url"],"/api-proxy/angular-solr")
    offset = int(source.get("resume") or 24)
    for start in [0,offset,offset+24,offset+48]:
        payload = _get(endpoint,_api_proxy_uri="news",q="*:*",sort="ds_field_publication_date DESC",
                       rows=24,start=start,**{"fq[]":["sm_news_type_name:Article","sm_research_area_name:[* TO *]"]}).json()["response"]
        for row in payload["docs"]:
            if not row["ss_url"].startswith("/news/"):
                continue
            title = row["ss_title"]
            if re.search(r"\b(wins?|awarded|receives?|named|joins|honor(?:s|ed)?|elected|memorial|obituary)\b.{0,50}\b(prize|award|professor|medal|fellow|faculty)\b",title,re.I):
                continue
            yield urljoin(source["url"],row["ss_url"]),title,None
        if start+24>=payload["numFound"]:
            source["continue_at"]=24
            break
        source["continue_at"]=start+24


@lru_cache(maxsize=256)
def _hugging_face_author(username):
    response=_get("https://huggingface.co/api/users/"+username+"/overview",missing_ok=True)
    if response is None:
        return False
    profile=response.json()
    return any(org.get("name")=="huggingface" for org in profile.get("orgs",[]))


def _hf(source):
    offset=int(source.get("resume") or 1)
    for page in [0,offset,offset+1]:
        response=_get(source["url"],p=page)
        soup=BeautifulSoup(response.content,"html.parser")
        for link in soup.select('main a[href^="/blog/"]:has(h2)'):
            path=link["href"]
            if not re.fullmatch(r"/blog/[\w-]+",path):
                continue  # community blogs have a separate author namespace
            url=urljoin(source["url"],path)
            response=_get(url,missing_ok=True)
            if response is None or urlsplit(response.url).hostname!="huggingface.co":
                continue
            article=BeautifulSoup(response.content,"html.parser")
            # Author cards below the H1; avatar upvoter lists are not authors.
            authors={a["href"][1:] for a in article.select('.blog-content div.leading-tight a[href]')
                     if re.fullmatch(r"/[\w.-]+",a["href"])}
            if authors and any(_hugging_face_author(name) for name in authors):
                yield url,link.h2.get_text(" ",strip=True),None
        next_link=next((a for a in soup.select('a[href]') if a.get_text(' ',strip=True)=="Next"),None)
        if next_link is None:
            source["continue_at"]=1
            break
        source["continue_at"]=page+1


def entries(source):
    if source["id"]=="26":
        yield from _jina(source)
    elif source["id"]=="29":
        yield from _mit(source)
    elif source["id"]=="25":
        yield from _hf(source)
