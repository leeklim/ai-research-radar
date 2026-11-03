"""Read the complete, publisher-counted Google DeepMind Publications index."""
import re
from urllib.parse import urljoin,urlsplit
from bs4 import BeautifulSoup


def publications(source,fetch,day):
    index=source["url"]
    next_url=index
    seen_pages=set()
    records={}
    duplicates=[]
    declared=None
    row_count=0
    while next_url:
        if next_url in seen_pages or urlsplit(next_url).hostname!="deepmind.google":
            raise ValueError("DeepMind Publications 페이지 순환 또는 도메인 변경")
        seen_pages.add(next_url)
        page=fetch(next_url)
        soup=BeautifulSoup(page.content,"html.parser")
        counter=soup.select_one(".publication-count__text")
        match=re.search(r"([\d,]+)\s+publications?",counter.get_text(" ",strip=True),re.I) if counter else None
        if not match:
            raise ValueError("DeepMind 공식 출판물 건수를 확인하지 못함")
        count=int(match[1].replace(",",""))
        if declared is None:
            declared=count
        if count!=declared:
            raise ValueError("페이지를 읽는 동안 DeepMind 공식 건수가 변경됨")
        for a in soup.select("a.list-group__link"):
            url=urljoin(page.url,a["href"])
            if urlsplit(url).hostname!="deepmind.google" or not re.fullmatch(r"/research/publications/\d+/?",urlsplit(url).path):
                raise ValueError("DeepMind 출판물 링크 형식 변경")
            title=a.select_one(".list-group__description").get_text(" ",strip=True)
            date=day(a.select_one(".list-group__date").get_text(" ",strip=True))
            row_count+=1
            key=url.rstrip("/")
            if key in records:
                duplicates.append(dict(url=url,title=title,first_page=records[key][3],repeated_page=page.url))
            else:
                records[key]=(url,title,date,page.url)
        nxt=soup.select_one('a[aria-label="Next page"][href]:not([href="#"]):not([aria-disabled="true"])')
        next_url=urljoin(page.url,nxt["href"]) if nxt else None
    if row_count!=declared:
        raise ValueError(f"DeepMind 공식 {declared}행 중 {row_count}행 확인")
    source["index_summary"]=dict(reported=declared,unique=len(records),pages=len(seen_pages),duplicates=duplicates)
    for url,title,date,page in records.values():
        source["found_on"]=page
        yield url,title,date
