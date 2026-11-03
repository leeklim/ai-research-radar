"""Retriable CSAIL publications adapter for the catalog linked by MIT."""
import re
import requests

SCOPE="a099ca0a-5497-44fb-9fd4-6900bf7e205b"
ENDPOINT="https://dspace.mit.edu/server/api/discover/search/objects"

def entries(source):
    # Always revisit the newest records; title-sorted traversal avoids large tie
    # sets in year-only issue dates that lost items across original page boundaries.
    resume=int(source.get("resume") or 0)
    for sort,number in [("dc.date.issued,DESC",0),("dc.title,ASC",resume),("dc.title,ASC",resume+1)]:
        r=requests.get(ENDPOINT,params=dict(scope=SCOPE,dsoType="item",sort=sort,page=number,size=100),
                       headers={"User-Agent":"AIResearchRadar/1.0 (https://github.com/leeklim/ai-research-radar)"},timeout=20)
        r.raise_for_status()
        result=r.json()["_embedded"]["searchResult"]
        source["found_on"]=r.url
        for wrapper in result.get("_embedded",{}).get("objects",[]):
            item=wrapper["_embedded"]["indexableObject"]
            handle=item.get("handle","")
            if not re.fullmatch(r"1721\.1/\d+(?:\.\d+)?",handle):continue
            values=item.get("metadata",{}).get("dc.date.issued",[])
            date=values[0]["value"] if values else None
            yield "https://dspace.mit.edu/handle/"+handle,item["name"],date if date and re.fullmatch(r"\d{4}(?:-\d{2}(?:-\d{2})?)?",date) else None
        if sort=="dc.title,ASC":
            source["continue_at"]=number+1 if number+1<result["page"]["totalPages"] else 0
            if source["continue_at"]==0:break
