"""OpenAI's own topic sitemaps give candidates. Require a visible article-header
link back to the human-visible publication index; no mixed newsroom tags.
Use max_new to bound each run; preserve the cursor separately if sweeping."""
import re
from datetime import datetime
from urllib.parse import urljoin,urlsplit
from xml.etree import ElementTree as ET
from bs4 import BeautifulSoup

TARGET='/research/index/publication'
MONTH='January|February|March|April|May|June|July|August|September|October|November|December'
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

