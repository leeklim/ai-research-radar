"""Parse only the Publication cards in the Meta AI publication-filtered results."""
from urllib.parse import urljoin,urlsplit


def cards(soup,page_url,day):
    if not soup.find("h1",string=lambda t:t and t.strip()=="Publications"):
        raise ValueError("Meta AI Publications 목록 제목 확인 실패")
    for link in soup.select("a[href]"):
        if link.get_text(" ",strip=True).casefold()!="read the paper":
            continue
        url=urljoin(page_url,link["href"])
        dest=urlsplit(url)
        if dest.hostname!="ai.meta.com" or not dest.path.startswith("/research/publications/"):
            raise ValueError(f"Meta 출판물 링크 형식 변경: {dest.hostname}")
        card=next((parent for parent in link.parents if parent.find("h4")
                   and any(tag.get_text(strip=True)=="Publication" for tag in parent.find_all("p"))),None)
        if not card:
            raise ValueError("Meta 출판물 카드 확인 실패")
        title=" ".join(card.find_all("h4")[-1].stripped_strings)
        date=next((d for p in card.find_all("p") if (d:=day(p.get_text(" ",strip=True)))),None)
        yield url," ".join(title.split()),date
