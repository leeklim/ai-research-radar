import json, hashlib, re, time
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, urldefrag
import requests, feedparser
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[1]
sources=json.loads((ROOT/'config/sources.json').read_text())
output=ROOT/'docs/data.json'
old=json.loads(output.read_text()) if output.exists() else {'items':[]}
items={x['id']:x for x in old['items']}
status={}
now=datetime.now(timezone.utc).isoformat(timespec='seconds')
keywords=re.compile(r'research|paper|publication|article|blog|post|news|202[0-9]|arxiv|release',re.I)
headers={'User-Agent':'AIResearchRadar/0.1 (research monitoring; contact via repository)'}

def normalize(href,base):
    u=urldefrag(urljoin(base,href or ''))[0]
    return u if urlparse(u).scheme in ('http','https') else None

def add(s,url,title,published=None):
    title=' '.join(title.split())
    if not url or len(title)<12 or len(title)>220:return
    key=hashlib.sha256((s['id']+'|'+url.rstrip('/')).encode()).hexdigest()[:20]
    if key not in items:
        items[key]={'id':key,'source':s['id'],'url':url,'title':title,'discovered':now,'published':published}
    elif published and not items[key].get('published'):
        items[key]['published']=published

def collect(s):
    r=requests.get(s['url'],headers=headers,timeout=15);r.raise_for_status()
    soup=BeautifulSoup(r.text,'html.parser')
    feeds=[normalize(x.get('href'),s['url']) for x in soup.select('link[rel="alternate"]') if 'rss' in x.get('type','') or 'atom' in x.get('type','')]
    for feed in feeds[:2]:
        if urlparse(feed).netloc!=urlparse(s['url']).netloc:continue
        try:
            f=feedparser.parse(requests.get(feed,headers=headers,timeout=15).content)
            if f.entries:
                for e in f.entries[:40]:
                    published=e.get('published') or e.get('updated')
                    add(s,normalize(e.get('link'),feed),BeautifulSoup(e.get('title',''),'html.parser').get_text(' ',strip=True),published)
                return
        except requests.RequestException:pass
    for x in soup(['script','style','nav','footer','header']):x.decompose()
    anchors=soup.select('main a[href], article a[href], [role=main] a[href]') or soup.select('a[href]')
    seen=set()
    for a in anchors:
        u=normalize(a.get('href'),s['url'])
        if not u or u in seen or u.rstrip('/')==s['url'].rstrip('/'):continue
        host=urlparse(u).netloc.removeprefix('www.')
        own=urlparse(s['url']).netloc.removeprefix('www.')
        if host!=own and host not in ('arxiv.org','github.com','huggingface.co'):continue
        if not keywords.search(urlparse(u).path) and not a.find_parent('article'):continue
        if re.search(r'privacy|terms|career|contact|login|signup',u,re.I):continue
        seen.add(u);add(s,u,a.get_text(' ',strip=True))
        if len(seen)>=40:break

for s in sources:
    try:
        before=len(items);collect(s);status[s['id']]={'ok':True,'new':len(items)-before}
    except (requests.RequestException,ValueError) as e:
        status[s['id']]={'ok':False,'error':str(e)[:120]}
    print(s['name'],status[s['id']],flush=True)
    time.sleep(.3)
output.write_text(json.dumps({'updated':now,'items':sorted(items.values(),key=lambda x:x['discovered'],reverse=True)[:2500],'status':status},ensure_ascii=False,indent=2))
