"""IBM publication evidence. URL paths and the presence of an Abstract alone do not establish a paper."""
import re
from urllib.parse import urlsplit


def catalog(source,fetch,day):
    """Read the same publication records and type metadata that power IBM's index."""
    offset=source.get("resume")
    offset=int(offset) if str(offset).isdigit() else 250
    for start in dict.fromkeys((0,offset)):
        query=('{publications(first:250,after:"%d",sortBy:FEATURED){totalCount '
               'nodes{title slug published abstract type{displayValue} publishedMeta{source year}}}}')%(start-1)
        from urllib.parse import urlencode
        result=fetch("https://research.ibm.com/graphql?"+urlencode({"query":query})).json()
        if result.get("errors") or not result.get("data",{}).get("publications"):
            raise ValueError("IBM Publications 목록을 읽지 못함")
        catalog=result["data"]["publications"]
        for row in catalog["nodes"]:
            meta=row.get("publishedMeta") or {}
            url=source["url"].rstrip("/")+"/"+row["slug"]
            e=dict(title=row["title"],kind=(row.get("type") or {}).get("displayValue") or "",
                   venue=meta.get("source") or "",abstract=row.get("abstract") or "")
            if not ibm_research_paper(e):
                source.setdefault("nonpapers",set()).add(url)
                continue
            source.setdefault("paper_metadata",{})[url]=(e["kind"],e["venue"])
            yield url,e["title"],day(str(row.get("published") or meta.get("year") or ""))
        source["continue_at"]=start+250 if start+250<catalog["totalCount"] else 250

# IBM uses "Paper" on journal publications and arXiv records, not only "Journal paper".
PAPER_TYPES = {"Paper","Conference paper","Workshop paper","Journal paper","Short paper",
               "Demo paper","Invited paper","Survey paper","Review","Poster","Workshop poster"}
NONRESEARCH_TITLE = re.compile(
    r"^\s*(?:\(?guest editorial\b|editorial\b|foreword\b|preface\b|errat(?:um|a)\b|"
    r"corrigendum\b|correction to\b|publisher.s note\b|cover (?:art|image|illustration)\b|"
    r"book reviews?\b|table of contents\b|call for (?:papers|posters|participation)\b|"
    r"opening remarks\b|proceedings of (?:the|a)\b|introduction to (?:the|this) special issue\b)|"
    r"\[(?:guest editorial|editorial|book review)\]",re.I)
POSTER_RESULT = re.compile(
    r"\b(?:we (?:have )?(?:stud(?:y|ied)|investigat\w*|introduc\w*|develop\w*|propos\w*|"
    r"evaluat\w*|demonstrat\w*|show\w*|present\w*|measure\w*|design\w*|report\w*|"
    r"analy[sz]\w*|observ\w*|experiment\w*|implement\w*)|(?:our|experimental|numerical|simulation) "
    r"(?:results?|experiments?|evaluation|measurements?)|experiments? (?:show|demonstrate)|"
    r"(?:measurements?|results?) (?:show|indicate|demonstrate)|\d+(?:\.\d+)?\s*%)",re.I)


def ibm_evidence(soup, final_url):
    addr=urlsplit(final_url)
    heading=soup.select_one("main header h1")
    if addr.hostname!="research.ibm.com" or not re.fullmatch(r"/publications/[^/]+/?",addr.path) or not heading:
        return None
    header=heading.find_parent("header")
    venue_link=header.select_one('a[href*="source-instance="],a[href*="?source="]')
    venue=venue_link.get_text(" ",strip=True) if venue_link else ""
    types=[e.get_text(" ",strip=True) for e in header.find_all("div",recursive=False) if not e.find(["a","time"])]
    kind=next((t for t in types if t), "")
    section=next((h for h in soup.select("main h2") if h.get_text(strip=True)=="Abstract"),None)
    body=section.find_next_sibling() if section else None
    abstract=body.get_text(" ",strip=True) if body else ""
    canonical=soup.select_one('link[rel~="canonical"][href]')
    if canonical and urlsplit(canonical["href"])[:3]!=addr[:3]:
        return None
    return {"kind":kind,"venue":venue,"title":heading.get_text(" ",strip=True),"abstract":abstract}


def ibm_research_paper(evidence):
    if not evidence or evidence["kind"] not in PAPER_TYPES or not evidence["venue"] or not evidence["abstract"]:
        return False
    # Keep empirical, theoretical, position, and methods papers. In particular a
    # "Workshop paper" is not a workshop invitation. A publisher mislabeled this
    # roadmap presentation as Conference paper; the Abstract identifies its format.
    abstract=evidence["abstract"].strip()
    if NONRESEARCH_TITLE.search(evidence["title"]):
        return False
    if re.search(r"^\s*(?:this (?:article|paper) is (?:a|an) (?:book review|editorial|erratum)|"
                 r"this (?:book review|editorial|foreword|preface)\b|in this (?:book review|editorial)\b)",abstract,re.I):
        return False
    if re.search(r"\bthis presentation outlines a forward[- ]looking roadmap\b",abstract,re.I):
        return False
    if evidence["kind"]=="Review":
        return len(abstract.split())>=25
    if evidence["kind"] in ("Poster","Workshop poster"):
        return len(abstract.split())>=25 and bool(POSTER_RESULT.search(abstract))
    return True
