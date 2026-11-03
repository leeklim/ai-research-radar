"""IBM publication evidence. URL paths and the presence of an Abstract alone do not establish a paper."""
import re
from urllib.parse import urlsplit

# IBM uses "Paper" on journal publications and arXiv records, not only "Journal paper".
PAPER_TYPES = {"Paper", "Conference paper", "Workshop paper", "Journal paper"}


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
    abstract=evidence["abstract"]
    if re.search(r"\bthis presentation outlines a forward[- ]looking roadmap\b",abstract,re.I):
        return False
    return True
