#!/usr/bin/env python3
"""Vendor the real river channel of the 26 Aug 2026 Trishuli flood from OpenStreetMap.

The 3D replay places the flood FRONT by kilometres along a polyline. A polyline
drawn between named places climbs over ridges; the water did not. This script
stitches the actual channel — Lhende Khola (OSM: 东林藏布) → Bhote Koshi →
Trishuli → Narayani — out of OSM waterway ways and writes it, densified to a
fixed step with cumulative km, to app/data/flood_river_path_trishuli_2026.json.

km 0 is Rasuwagadhi (the border post the surge destroyed), matching every km
mark the desk already publishes. Upstream is negative. The upstream end is cut
at the NDRRMA-stated source zone, "approximately 20 km upstream of
Rasuwagadhi" on the Lhende (SitRep #01, 1 Sep 2026); nothing above it is
mapped, and nothing above it is drawn.

Run:  python3 scripts/build_river_path.py [--overpass osm_rivers.json]
Data © OpenStreetMap contributors, ODbL. Re-run to refresh; the output records
the way ids it used so a change in OSM is auditable.
"""
import argparse, collections, datetime, heapq, json, math, sys, urllib.request
from pathlib import Path

R = 6371.0088
OUT = Path(__file__).resolve().parent.parent / "app" / "data" / "flood_river_path_trishuli_2026.json"
QUERY = """[out:json][timeout:120];
(
  way["waterway"="river"](27.35,84.20,28.75,85.75);
  way["waterway"="stream"]["name"~"Lende|Lhende|Langtang|Trisuli|Trishuli|Bhote",i](28.0,85.2,28.75,85.75);
);
out geom;"""
RASUWAGADHI = (28.278, 85.379)      # km 0 — corridor waypoint the desk publishes
DEVGHAT = (27.716, 84.428)          # downstream end of the record
LHENDE_UPPER = (28.438, 85.442)     # upstream end of the mapped Lhende (东林藏布)
SOURCE_KM_UPSTREAM = 20.0           # NDRRMA SitRep #01: "~20 km upstream of Rasuwagadhi"
STEP_M = 100.0

def hav(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))

def fetch(overpass_cache):
    if overpass_cache and Path(overpass_cache).exists():
        return json.load(open(overpass_cache))
    req = urllib.request.Request("https://overpass-api.de/api/interpreter",
                                 data=("data=" + urllib.parse.quote(QUERY)).encode(),
                                 headers={"User-Agent": "NepalOSINT/5.0 (flood desk; +https://nepalosint.com)"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)

def build_graph(data):
    adj = collections.defaultdict(list); coord = {}; name_of = {}; way_of = {}
    for w in data["elements"]:
        if w.get("type") != "way" or "geometry" not in w: continue
        nm = w.get("tags", {}).get("name") or w.get("tags", {}).get("name:en") or ""
        ids = w.get("nodes") or [None] * len(w["geometry"])
        pts = [(g["lat"], g["lon"]) for g in w["geometry"]]
        keys = []
        for i, pt in enumerate(pts):
            k = ids[i] if ids[i] is not None else ("c", round(pt[0], 5), round(pt[1], 5))
            coord[k] = pt; keys.append(k); name_of.setdefault(k, nm)
        for i in range(len(keys) - 1):
            a, b = keys[i], keys[i + 1]; d = hav(pts[i], pts[i + 1])
            adj[a].append((b, d, w["id"], True)); adj[b].append((a, d, w["id"], False))
    return adj, coord, name_of

def nearest(coord, pt):
    return min(coord, key=lambda k: hav(coord[k], pt))

def dijkstra(adj, src, dst, directed=True):
    dist = {src: 0.0}; prev = {}; pq = [(0.0, src)]
    while pq:
        dd, u = heapq.heappop(pq)
        if u == dst: break
        if dd > dist.get(u, 1e18): continue
        for v, w, wid, fwd in adj[u]:
            if directed and not fwd: continue
            nd = dd + w
            if nd < dist.get(v, 1e18): dist[v] = nd; prev[v] = (u, wid); heapq.heappush(pq, (nd, v))
    if dst not in dist: return None
    path, ways, u = [], [], dst
    while u != src:
        path.append(u); ways.append(prev[u][1]); u = prev[u][0]
    path.append(src); path.reverse()
    return path, sorted(set(ways))

def densify(pts, step_km):
    out = [pts[0]]; carry = 0.0
    for a, b in zip(pts, pts[1:]):
        seg = hav(a, b)
        if seg == 0: continue
        pos = step_km - carry
        while pos < seg:
            f = pos / seg
            out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)); pos += step_km
        carry = seg - (pos - step_km)
    out.append(pts[-1]); return out

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--overpass"); ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    data = fetch(args.overpass)
    adj, coord, name_of = build_graph(data)
    k_up, k_r, k_d = nearest(coord, LHENDE_UPPER), nearest(coord, RASUWAGADHI), nearest(coord, DEVGHAT)
    up = dijkstra(adj, k_up, k_r); down = dijkstra(adj, k_r, k_d)
    if not up or not down: sys.exit("no directed channel found: up=%s down=%s" % (bool(up), bool(down)))
    pts = [coord[k] for k in up[0]] + [coord[k] for k in down[0][1:]]
    # cumulative km with 0 at Rasuwagadhi
    cum = [0.0]
    for a, b in zip(pts, pts[1:]): cum.append(cum[-1] + hav(a, b))
    k0 = cum[len(up[0]) - 1]
    km = [c - k0 for c in cum]
    # cut the upstream end at the NDRRMA source zone
    start = next(i for i, v in enumerate(km) if v >= -SOURCE_KM_UPSTREAM)
    if start > 0 and km[start] > -SOURCE_KM_UPSTREAM:
        f = (-SOURCE_KM_UPSTREAM - km[start - 1]) / (km[start] - km[start - 1])
        a, b = pts[start - 1], pts[start]
        pts = [(a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)] + pts[start:]
    else:
        pts = pts[start:]
    dense = densify(pts, STEP_M / 1000.0)
    cum = [0.0]
    for a, b in zip(dense, dense[1:]): cum.append(cum[-1] + hav(a, b))
    i0 = min(range(len(dense)), key=lambda i: hav(dense[i], RASUWAGADHI))
    kmd = [round(c - cum[i0], 4) for c in cum]
    names = collections.Counter(name_of.get(k, "") for k in up[0] + down[0])
    out = {
        "event_key": "trishuli-2026-08",
        "source": "OpenStreetMap waterway ways, stitched by directed shortest path along digitised flow direction",
        "attribution": "Channel geometry © OpenStreetMap contributors, ODbL",
        "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "km0": {"name": "Rasuwagadhi", "lat": RASUWAGADHI[0], "lng": RASUWAGADHI[1]},
        "upstream_cut": {"km": -SOURCE_KM_UPSTREAM,
                          "reason": "NDRRMA SitRep #01 (1 Sep 2026): source zone on a north-facing slope near the Lhende River, approximately 20 km upstream of Rasuwagadhi; the channel above the mapped Lhende is not drawn",
                          "source_url": "https://ndrrma.gov.np/mediafiles/rasuwa/Rasuwa_Flood_SitRep_Temp_ENG_01_01092026.pdf"},
        "step_m": STEP_M,
        "length_km": round(kmd[-1] - kmd[0], 2),
        "osm_way_ids": sorted(set(up[1] + down[1])),
        "channel_names": [n for n, _ in names.most_common() if n],
        "vertices": [[round(p[1], 6), round(p[0], 6), k] for p, k in zip(dense, kmd)],
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    print(f"wrote {args.out}: {len(out['vertices'])} vertices, {out['length_km']} km, km range {kmd[0]:.1f}..{kmd[-1]:.1f}, ways {len(out['osm_way_ids'])}")
    print("channels:", out["channel_names"])
    for nm, pt in {"Syabrubesi": (28.160, 85.348), "Betrawati": (27.975, 85.180), "Galchhi": (27.851, 85.007), "Malekhu": (27.807, 84.826), "Mugling": (27.856, 84.564), "Devghat": DEVGHAT}.items():
        i = min(range(len(dense)), key=lambda i: hav(dense[i], pt)); print(f"  {nm:12s} km {kmd[i]:7.1f}  off-channel {hav(dense[i], pt):.2f} km")

if __name__ == "__main__":
    import urllib.parse
    main()
