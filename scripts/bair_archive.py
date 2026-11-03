"""Dated research entries, as linked from the BAIR Archive."""
import re
from datetime import datetime
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from collect import fetch


def entries(source):
    soup=BeautifulSoup(fetch(source["url"]).content,"html.parser")
    for link in soup.select('p a[href^="/blog/"]'):
        href=link["href"]
        if not re.fullmatch(r"/blog/\d{4}/\d{2}/\d{2}/[^/]+/",href):
            continue
        title=link.get_text(" ",strip=True)
        if (re.search(r"\b(?:BAIR Graduate (?:Directory|Showcase)|newsletter|event recap|hiring)\b",title,re.I)
                or title in {"Introducing the BAIR Blog","Announcing the BAIR Open Research Commons"}):
            continue
        label=link.parent.get_text(" ",strip=True).split("»",1)[0].strip()
        try:
            visible_day=datetime.strptime(label,"%d %b %Y").date().isoformat()
        except ValueError:
            visible_day=None
        yield urljoin(source["url"],href),title,visible_day
