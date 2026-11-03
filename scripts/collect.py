"""Collect individual research outputs from publication catalogs and author affiliations."""
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")
TYPES = "article|preprint|dissertation"
ARXIV = re.compile(r"/(?:pdf|abs|papers)/(\d{4}\.\d{4,5})(?:v\d+)?(?:\.pdf)?/?$")
HEADERS = {"User-Agent": "AIResearchRadar/1.0 (https://github.com/leeklim/ai-research-radar)"}


def get(url, **params):
    response = requests.get(url, params=params, headers=HEADERS, timeout=18)
    response.raise_for_status()
    return response


def match_affiliation(source, affiliation):
    term = source["affiliation"]
    normalized = re.sub(r"[^\w]+", " ", affiliation.casefold()).strip()
    words = re.sub(r"[^\w]+", " ", term.casefold()).strip()
    if term in ("Apple", "Amazon", "xAI"):
        company = r"(?: inc| llc| ai| research| robotics| com| web services| science| development center)?"
        place = r"(?: (?:cupertino|seattle|california|usa|united states|palo alto|ca|wa|\d+))*"
        return bool(re.fullmatch(re.escape(words) + company + place, normalized))
    return (bool(re.search(r"\b" + re.escape(words) + r"\b", normalized))
            and (not source.get("also") or re.search(r"\b(?:"+source["also"]+r")\b", normalized)))


def indexed(source):
    term = source["affiliation"]
    result = get("https://api.openalex.org/works", filter=f'raw_affiliation_strings.search:"{term}",type:{TYPES},to_publication_date:{NOW[:10]}',
                 sort="publication_date:desc", per_page=50, select="title,doi,publication_date,primary_location,authorships").json()
    for work in result["results"]:
        if not any(match_affiliation(source, a) for author in work["authorships"]
                   for a in author.get("raw_affiliation_strings", [])):
            continue
        link = work.get("doi") or (work.get("primary_location") or {}).get("landing_page_url")
        if link and "10.5281/zenodo." not in link.lower() and urlsplit(link).scheme in ("https","http"):
            yield link, work["title"], work["publication_date"], "논문 · 소속 확인"


def catalog(source):
    base = source["url"]
    soup = BeautifulSoup(get(base).content, "html.parser")
    for noise in soup.select("header,footer,nav,aside,script,style"):
        noise.decompose()
    for anchor in soup.select("a[href]"):
        href = urljoin(base, anchor["href"])
        u = urlsplit(href)
        paper = ARXIV.fullmatch(u.path)
        if paper and u.hostname in ("arxiv.org","www.arxiv.org","huggingface.co"):
            href = "https://arxiv.org/abs/"+paper[1]
        elif not (source.get("path") and u.hostname == urlsplit(base).hostname and not u.query
                  and not u.fragment and re.fullmatch(source["path"], u.path, re.I)):
            continue
        label = anchor.select_one("h2,h3,h4") or anchor
        title = " ".join(label.get_text(" ",strip=True).split())
        if u.fragment or re.fullmatch(r"[\W\d]*(?:authors?|comments?|upvotes?|paper|pdf|full text|read paper)[\W\d]*",title,re.I):
            continue
        if len(title) < 9 or len(title) > 350 or title.lower().startswith(("view all","see all","browse all")):
            continue
        published = None
        if source["id"] == "3":
            date_label = anchor.select_one(".index-meta span:last-child")
            if date_label:
                try:
                    published = datetime.strptime(date_label.get_text(strip=True), "%B %d, %Y").date().isoformat()
                except ValueError:
                    pass
        yield href, title, published, "연구 결과" if source["id"]=="3" else "논문 · 기관 목록"


def collect(source):
    results, errors = [], []
    for enabled, method in [(source.get("catalog"),catalog),(source.get("affiliation"),indexed)]:
        if enabled:
            try:
                results.extend(method(source))
            except (requests.RequestException, ValueError) as exc:
                errors.append(f"{method.__name__}: {exc}"[:160])
    return source, results, errors


def main():
    sources = json.loads((ROOT/"config/sources.json").read_text("utf8"))
    output = ROOT/"docs/data.json"
    old = {x["id"]:x for x in json.loads(output.read_text("utf8"))["items"]}
    # Carry over only previously verified outputs. Reuse discovery dates for revalidated legacy URLs.
    items = {k:v for k,v in old.items() if v.get("kind")}
    status = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for source, results, errors in pool.map(collect, sources):
            seen = set()
            for url,title,date,kind in results:
                if not title: continue
                url = re.sub(r"^https://doi.org/10\.48550/arxiv\.(\d{4}\.\d{4,5})$",r"https://arxiv.org/abs/\1",url,flags=re.I)
                key = hashlib.sha256((source["id"]+"|"+url.rstrip("/")).encode()).hexdigest()[:20]
                seen.add(key)
                prev = items.get(key) or old.get(key) or {}
                items[key] = dict(id=key, source=source["id"], title=title, url=url, kind=kind,
                                  discovered=prev.get("discovered",NOW), published=date or prev.get("published"))
            status[source["id"]] = dict(ok=bool(seen), count=len(seen), partial=bool(seen and errors), error=" / ".join(errors))
            print(source["name"],len(seen),"/".join(errors)[:90],flush=True)
    ordered = sorted(items.values(), key=lambda x: x["published"] or "", reverse=True)
    tmp = output.with_suffix(".tmp")
    tmp.write_text(json.dumps(dict(updated=NOW,items=ordered,status=status),ensure_ascii=False,indent=2),"utf8")
    tmp.replace(output)


if __name__ == "__main__":
    main()

