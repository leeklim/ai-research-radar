"""Publications explicitly linked in Mila's official title cards."""
import re
from urllib.parse import urlsplit,parse_qs,urlencode,quote

PAPER_LINKS={
    # Only constructed for the two verified author/abstract cards below.
    "mila.quebec": r"/en/research/publications",
    "openreview.net": r"/(?:forum|pdf)",
    "doi.org": r"/10\.\d{4,9}/.+",
    "arxiv.org": r"/(?:abs|pdf)/(?:[\w.-]+/)?[\w.-]+/?",
    "proceedings.mlr.press": r"/v\d+/[\w.-]+(?:/[\w.-]+)?",
    "www.semanticscholar.org": r"/paper/[\w%.-]+(?:/[\w.-]+)?/?",
    "dblp.uni-trier.de": r"/rec/[\w./%+-]+",
    "openalex.org": r"/W\d+/?",
    "pubmed.ncbi.nlm.nih.gov": r"/\d+/?",
}
LINKLESS_TITLES={
    "From Where Things Are to What They Are For: Benchmarking Spatial–Functional Intelligence in Multimodal LLMs",
    "Automatic differentiation in ML: Where we are and where we should be going",
}
# Abstract when available rather than a PDF, with explicit OpenReview priority.
PRIORITY=("openreview.abstract","openreview.pdf","doi.abstract","mlr.abstract","arxiv.abstract",
          "arxiv.pdf","mlr.pdf","pubmed.abstract","semantic_scholar.abstract","dblp.abstract","openalex.abstract")

def rank(link):
    u=urlsplit(link["url"])
    return PRIORITY.index(link["rel"]) if link["rel"] in PRIORITY else len(PRIORITY)

def direct(link):
    parsed=urlsplit(link["url"]);pattern=PAPER_LINKS.get(parsed.netloc)
    if parsed.scheme not in ("https","http") or not pattern or not re.fullmatch(pattern,parsed.path):
        return False
    if parsed.netloc=="openreview.net":
        ids=parse_qs(parsed.query).get("id",[])
        return len(ids)==1 and re.fullmatch(r"[\w-]+",ids[0]) is not None
    return True

def parse_cards(soup):
    for card in soup.select(".mila-publication"):
        title=card.select_one(".field-name-title")
        dates=[];links=[]
        for block in card.select(".field-name-links .field-item"):
            tag=block.select_one(".publication-date")
            when=tag.get_text(" ",strip=True) if tag else None
            if when:dates.append(when)
            for a in block.select(".publication-url a[href]"):
                links.append(dict(url=a["href"].strip(),rel=a.parent.get("data-type"),date=when))
        yield dict(title=title.get_text(" ",strip=True) if title else "",links=links,dates=dates)

def pick(card):
    links=[l for l in card["links"] if direct(l)]
    if not card["title"]:return None
    if not links:
        if card["title"] not in LINKLESS_TITLES:return None
        # The card has authors and an abstract but no href/id. These official
        # search URLs were checked for exactly one matching visible full title.
        # A title-based search remains stable when new results shift its page.
        title=card["title"]
        url="https://mila.quebec/en/research/publications?"+urlencode({"s":title.split(":",1)[0]})+"#:~:text="+quote(title,safe="")
        return url,title,None
    first=min(links,key=rank)
    date=first.get("date") or next(iter(card["dates"]),None)
    date=date if date and re.fullmatch(r"\d{4}(?:-\d{2}(?:-\d{2})?)?",date) else None
    return first["url"],card["title"],date
