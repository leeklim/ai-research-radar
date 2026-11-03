"""Read the publication archives used by Cohere and ByteDance Seed."""
import json
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


def _get(url, **kwargs):
    headers = {"User-Agent": "AIResearchRadar/1.0 (https://github.com/leeklim/ai-research-radar)"}
    headers.update(kwargs.pop("headers", {}))
    response = requests.get(url, headers=headers, timeout=15, **kwargs)
    response.raise_for_status()
    return response


def _embedded_list(url, key):
    """Read the initial client component props behind the site's More control."""
    soup = BeautifulSoup(_get(url).content, "html.parser")
    prefix = "self.__next_f.push("
    for node in soup.select("script"):
        script = (node.string or "").strip().rstrip(";")
        if not script.startswith(prefix) or not script.endswith(")"):
            continue
        chunk = json.loads(script[len(prefix):-1])
        if len(chunk) < 2 or not isinstance(chunk[1], str):
            continue
        match = re.search(r'"' + re.escape(key) + r'":\s*(?=\[)', chunk[1])
        if match:
            return json.JSONDecoder().raw_decode(chunk[1][match.end():])[0]
    raise ValueError("공식 목록의 더보기 데이터를 읽지 못함")


def _seed(s):
    papers = s["url"].endswith("/public_papers")
    size = 20 if papers else 12
    token = "0"
    seen = set()
    while token not in seen:
        seen.add(token)
        payload = _get("https://seed.bytedance.com/api/get_article_list_v2", headers={
            "X-Tt-Locale":"US","Referer":s["url"],"Accept-Language":"en-US"}, params={
            "article_type":1 if papers else 2,"query":"","page_token":token,
            "count":size,"order_desc":"true","publish_year":"",
            "research_area_id":s.get("area_id",""),"work_team_id":""}).json()
        if "sub_article_list" not in payload and payload.get("total"):
            raise ValueError("Seed 영문 목록 데이터를 받지 못함")
        for post in payload.get("sub_article_list",[]):
            content = post.get("ArticleSubContentEn") or {}
            slug, title = content.get("TitleKey"), content.get("Title")
            if not slug or not title:
                continue
            stamp = post.get("ArticleMeta",{}).get("PublishDate")
            date = datetime.fromtimestamp(stamp / 1000, timezone(timedelta(hours=8))).date().isoformat() if stamp else None
            path = "/en/public_papers/" if papers else "/en/blog/"
            yield urljoin(s["url"],path+slug),title,date
        if not payload.get("has_more"):
            return
        token = str(payload["next_page_token"])
    raise ValueError("Seed에서 중복된 페이지 토큰을 반환함")


def entries(s):
    url = s["url"]
    if s["id"] == "15":
        for post in _embedded_list(url,"papersList"):
            slug = (post.get("slug") or {}).get("current")
            if post.get("_type") == "researchPaper" and slug and post.get("heading"):
                yield url.rstrip("/")+"/"+slug,post["heading"],post.get("dateOfPublication")
    elif s["id"] == "18":
        yield from _seed(s)
