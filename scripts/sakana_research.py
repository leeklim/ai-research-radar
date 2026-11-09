"""Research-labeled Sakana articles, including co-tagged original results."""
import re
from datetime import datetime
from urllib.parse import urljoin,urlsplit

import requests
from bs4 import BeautifulSoup


UA={"User-Agent":"AIResearchRadar/1.0 (https://github.com/leeklim/ai-research-radar)"}

# These individual posts were checked against the original papers, reported
# experiments, named baselines, or substantive analyses on the official page.
REVIEWED_RESULTS={
    "/coffee-bench/", "/edinet-bench/", "/m2n2/",
    "/ai-scientist-nature/", "/ai-scientist-nature-jp/",
    "/ahc058/", "/ahc-2025/",
    "/fugu-release/", "/fugu-beta/", "/fugu-max-release/", "/fugu-gemma4/",
    "/fugu-cyber-release/", "/namazu-alpha/",
}
REVIEWED_NONSTUDIES={
    "/schmidhuber/","/nvidia-open-model-innovation/","/rsi-lab/","/rsi-lab-jp/",
    "/frontier-intelligence-group/","/fugu-1-1-claude-code-interface/",
}


def new_mixed_result(url):
    resp=requests.get(url,headers=UA,timeout=12)
    resp.raise_for_status()
    if urlsplit(resp.url).hostname!=urlsplit(url).hostname:return False
    article=BeautifulSoup(resp.content,"html.parser").select_one("article")
    if not article:return False
    title=article.select_one("h1")
    if title and re.search(r"\b(welcoming|joins our team|teams up with|partners with|we are hiring)\b",title.get_text(" ",strip=True),re.I):
        return False
    # A reference appearing in surrounding prose does not establish that the
    # article reports that paper. Require an actual paper/report callout.
    for a in article.select("a[href]"):
        href=urlsplit(a["href"])
        local_label=(a.parent.get_text(" ",strip=True) if a.parent else "")[:120]
        if href.hostname in ("arxiv.org","openreview.net","www.nature.com") and re.match(
            r"^(?:read (?:our |the )?|our )?(?:technical report|paper|preprint|論文|プレプリント|openreview)\b|^論文[:：]",
            local_label,re.I):
            return True
    body=article.get_text(" ",strip=True)
    # Preserve releases with their own experiments. Generic "state of the art"
    # announcements without a method, comparator, or measurement do not qualify.
    comparative=re.search(r"\bwe (?:evaluate[ds]?|compared|measured|tested|trained)\b|我々.{0,25}(?:評価|比較|検証)|訓練.{0,35}検証",body,re.I)
    quantitative=re.search(r"\d+(?:\.\d+)?\s*%|\b\d+(?:\.\d+)? points\b|実験結果|評価結果",body,re.I)
    return bool(comparative and quantitative)


def entries(s):
    response=requests.get(s["url"],headers=UA,timeout=15)
    response.raise_for_status()
    soup=BeautifulSoup(response.content,"html.parser")
    for post in soup.select("article[data-labels]"):
        labels={tag.strip().lower() for tag in post["data-labels"].split(",")}
        a=post.select_one("header h1 a[href]")
        if "research" not in labels or not a:continue
        url=urljoin(s["url"],a["href"])
        path=urlsplit(url).path
        if path in REVIEWED_NONSTUDIES:continue
        if labels!={"research"} and path not in REVIEWED_RESULTS and not new_mixed_result(url):continue
        stamp=post.select_one("header time")
        published=None
        if stamp:
            # The date is visibly rendered as "October 20, 2026" from this
            # element; retain the visibly displayed date, not the UTC instant.
            try:published=datetime.strptime(stamp.get_text(" ",strip=True),"%B %d, %Y").date().isoformat()
            except ValueError:pass
        yield url,a.get_text(" ",strip=True),published
