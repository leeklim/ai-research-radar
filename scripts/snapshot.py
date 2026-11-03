"""Store large official catalogs separately so an institution view can load just its own records."""
import json
from collections import Counter, defaultdict
from pathlib import Path


def read(path):
    data=json.loads(path.read_text("utf8"))
    if data.get("catalogs"):
        data["items"]=[row for group in data["catalogs"].values() for name in group["files"]
                       for row in json.loads((path.parent/name).read_text("utf8"))]
    return data


def write(path,updated,items,status):
    directory=path.parent/"catalog"
    directory.mkdir(exist_ok=True)
    by_source=defaultdict(list)
    for row in items:
        by_source[row["source"]].append(row)
    catalogs={}
    preview=[]
    by_day=Counter()
    keep=set()
    for source,records in by_source.items():
        records.sort(key=lambda row:row["id"])
        files=[]
        for start in range(0,len(records),4000):
            name=f"catalog/{source}-{start//4000}.json"
            files.append(name)
            keep.add(Path(name).name)
            text="[\n"+",\n".join(json.dumps(r,ensure_ascii=False,separators=(",",":")) for r in records[start:start+4000])+"\n]\n"
            (path.parent/name).write_text(text,"utf8")
        dated=[row for row in records if row.get("published")]
        by_day.update(row["published"] for row in dated if len(row["published"])==10)
        catalogs[source]=dict(files=files,count=len(records),dated=len(dated))
        ordered=sorted(records,key=lambda row:row["title"].casefold())
        ordered.sort(key=lambda row:row.get("published") or "",reverse=True)
        preview.extend(ordered[:40])
    data=dict(updated=updated,catalogs=catalogs,by_day=by_day,items=preview,status=status)
    tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data,ensure_ascii=False,separators=(",",":")),"utf8")
    tmp.replace(path)
    for previous in directory.glob("*.json"):
        if previous.name not in keep:
            previous.unlink()
