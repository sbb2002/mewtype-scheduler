"""공개 자료(USDA NAIP · USGS Landsat 9)로 풍경 표면 사진을 만든다.
Planetary Computer STAC 검색 → 아이템별 bbox 잘라 받기 → 한 장으로 이어 붙이기."""
import io, json, sys, urllib.request, urllib.parse
from PIL import Image

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
DATA = "https://planetarycomputer.microsoft.com/api/data/v1/item/bbox"
OUT = sys.argv[1]
N = 2048


def post(url, body):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=120))


def get(url):
    return urllib.request.urlopen(url, timeout=300).read()


def build(name, coll, bbox, dt, query, params, sort=None, limit=50):
    body = {"collections": [coll], "bbox": bbox, "datetime": dt, "limit": limit}
    if query:
        body["query"] = query
    if sort:
        body["sortby"] = sort
    feats = post(STAC, body)["features"]
    print(name, "items", len(feats), [f["id"] for f in feats[:6]])
    W, S, E, Nn = bbox
    canvas = Image.new("RGB", (N, N))
    mask = Image.new("L", (N, N))
    meta = []
    for f in feats:
        fb = f["bbox"]
        ib = [max(W, fb[0]), max(S, fb[1]), min(E, fb[2]), min(Nn, fb[3])]
        if ib[0] >= ib[2] or ib[1] >= ib[3]:
            continue
        x0 = round((ib[0] - W) / (E - W) * N); x1 = round((ib[2] - W) / (E - W) * N)
        y0 = round((Nn - ib[3]) / (Nn - S) * N); y1 = round((Nn - ib[1]) / (Nn - S) * N)
        w, h = x1 - x0, y1 - y0
        if w < 4 or h < 4:
            continue
        q = urllib.parse.urlencode([("collection", coll), ("item", f["id"])] + params)
        url = f"{DATA}/{ib[0]},{ib[1]},{ib[2]},{ib[3]}/{w}x{h}.png?{q}"
        im = Image.open(io.BytesIO(get(url))).convert("RGBA")
        a = im.getchannel("A")
        # 아직 안 칠한 자리만 채운다(앞 아이템 = 우선)
        free = Image.eval(mask.crop((x0, y0, x1, y1)), lambda v: 255 - v)
        use = Image.composite(a, Image.new("L", a.size), free)
        canvas.paste(im.convert("RGB"), (x0, y0), use)
        mask.paste(Image.eval(mask.crop((x0, y0, x1, y1)), lambda v: v), (x0, y0))
        mask.paste(255, (x0, y0, x1, y1), use)
        meta.append({"id": f["id"], "datetime": f["properties"].get("datetime"), "cloud": f["properties"].get("eo:cloud_cover")})
        print(" pasted", f["id"], w, h)
        if mask.getextrema() == (255, 255):
            break
    cov = sum(mask.histogram()[255:]) / (N * N)
    print(name, "coverage", round(cov, 4))
    canvas.save(f"{OUT}/{name}.png")
    canvas.save(f"{OUT}/{name}.webp", quality=88, method=6)
    json.dump({"bbox": bbox, "collection": coll, "items": meta, "coverage": cov}, open(f"{OUT}/{name}.json", "w"), indent=2)


which = sys.argv[2:] or ["city", "mountain"]
if "city" in which:
    # Denver 동쪽 도심 · Cherry Creek · 주택가 · City Park — 8 × 8km
    build("ground-city-albedo", "naip", [-104.977, 39.694, -104.883, 39.766], "2023-01-01/2023-12-31", None,
          [("assets", "image"), ("asset_bidx", "image|1,2,3")])
if "mountain" in which:
    # Front Range 산지(Evergreen 서쪽 ~ Mount Evans 북동) — 32 × 32km, 2024 여름 · 구름 ≤ 5%
    build("ground-mountain-albedo", "landsat-c2-l2", [-105.535, 39.530, -105.161, 39.818], "2024-07-01/2024-09-15",
          {"platform": {"eq": "landsat-9"}, "eo:cloud_cover": {"lt": 5}},
          [("assets", "red"), ("assets", "green"), ("assets", "blue"), ("nodata", "0"),
           ("color_formula", "gamma RGB 2.7, saturation 1.5, sigmoidal RGB 15 0.55")],
          sort=[{"field": "eo:cloud_cover", "direction": "asc"}], limit=1)
