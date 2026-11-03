import json
from urllib.parse import urljoin,urlsplit

DEPLOY="https://deploymentsafety.openai.com/"

def deployment_cards(soup,listing=DEPLOY):
    """Read the complete first-party array rendered by the Updates View more control."""
    node=soup.select_one("astro-island[component-export='UpdatesList'][props]")
    if node is None:raise ValueError("Deployment Safety UpdatesList is absent")
    encoded=json.loads(node["props"])["items"]
    if encoded[0]!=1:raise ValueError("Deployment Safety updates changed")
    for _,values in encoded[1]:
        def val(key,default=None):
            pair=values.get(key)
            return pair[1] if isinstance(pair,list) and len(pair)>1 else default
        if val("published") is not True or val("archived") or not val("href") or not val("title"):continue
        url=urljoin(listing,val("href"))
        if urlsplit(url).hostname==urlsplit(listing).hostname:
            yield url,val("title"),val("date")

