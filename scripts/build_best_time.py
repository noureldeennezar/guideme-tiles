#!/usr/bin/env python3
"""Builds best_time/best_time.json: for each destination, 12 months of real climate
averages and a 0-100 "how pleasant to visit" score. Free: NASA POWER climate averages
(public data, no key). Only destinations missing from the existing file are fetched,
because climate does not change from week to week.

    python scripts/build_best_time.py            # normal run
    python scripts/build_best_time.py --selftest # checks the scoring, no network
"""
import json, os, sys, time, datetime, urllib.request, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "best_time", "best_time.json")
MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
API = "https://power.larc.nasa.gov/api/temporal/climatology/point"


def clamp(v):
    return max(0, min(100, int(round(v))))


def month_score(kind, hi, lo, rain):
    """hi/lo: average daily max/min in C. rain: mm per day."""
    if kind == "beach":      # warm, sunny, dry
        s = 100 - 7 * max(0, 27 - hi) - 9 * max(0, hi - 33) - 10 * max(0, rain - 2)
    elif kind == "tropical":  # warm all year: the dry season is what matters
        s = 100 - 6 * max(0, 24 - hi) - 8 * max(0, hi - 32) - 14 * max(0, rain - 3)
    elif kind == "desert":   # avoid the furnace
        s = 100 - 6 * max(0, 20 - hi) - 8 * max(0, hi - 30) - 5 * max(0, rain - 1) - 3 * max(0, 3 - lo)
    elif kind == "nature":   # walking weather
        s = 100 - 6 * max(0, 15 - hi) - 7 * max(0, hi - 26) - 8 * max(0, rain - 2.5) - 3 * max(0, 0 - lo)
    else:                    # city
        s = 100 - 6 * max(0, 18 - hi) - 7 * max(0, hi - 27) - 8 * max(0, rain - 2) - 2 * max(0, 2 - lo)
    return clamp(s)


def fetch(lat, lng):
    q = urllib.parse.urlencode({
        "parameters": "T2M_MAX,T2M_MIN,PRECTOTCORR", "community": "RE",
        "longitude": lng, "latitude": lat, "format": "JSON"})
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(API + "?" + q, headers={"User-Agent": "guideme-best-time/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                p = json.load(r)["properties"]["parameter"]
            hi = [p["T2M_MAX"][m] for m in MONTHS]
            lo = [p["T2M_MIN"][m] for m in MONTHS]
            rain = [p["PRECTOTCORR"][m] for m in MONTHS]
            if any(v is None or v <= -900 for v in hi + lo + rain):
                raise ValueError("missing values")
            return hi, lo, rain
        except Exception as e:  # noqa
            last = e
            time.sleep(3 * (attempt + 1))
    raise last


META = ("id", "name", "country", "cc", "lat", "lng", "kind", "wiki")


def build(dest, prev=None):
    """Climate numbers are fetched once and kept; the scores are recomputed every run, so
    changing a scoring rule above never needs a new download."""
    d = {k: dest[k] for k in META if k in dest}
    if "fixed" in dest:
        d["fixed"] = dest["fixed"]
        d["score"] = list(dest["fixed"])
        return d
    if prev and prev.get("hi") and prev.get("lat") == dest["lat"] and prev.get("lng") == dest["lng"]:
        hi, lo, rain = prev["hi"], prev["lo"], prev["rain"]
    else:
        hi, lo, rain = fetch(dest["lat"], dest["lng"])
    d["hi"] = [int(round(v)) for v in hi]
    d["lo"] = [int(round(v)) for v in lo]
    d["rain"] = [round(v, 1) for v in rain]
    d["score"] = [month_score(dest["kind"], h, l, r) for h, l, r in zip(d["hi"], d["lo"], d["rain"])]
    return d


def selftest():
    # typical, well-known climates (rounded): the ranking must make sense
    ist = [month_score("city", h, l, r) for h, l, r in zip(
        [9, 9, 12, 17, 22, 27, 29, 29, 25, 20, 15, 11], [4, 4, 5, 9, 13, 18, 21, 21, 17, 14, 10, 6],
        [3.0, 2.4, 2.1, 1.5, 1.2, 0.9, 0.6, 0.7, 1.2, 2.5, 3.0, 3.6])]
    assert max(range(12), key=lambda i: ist[i]) in (4, 5, 8), ist  # May, Jun or Sep
    assert ist[0] < 50 and ist[4] > 85, ist
    cai = [month_score("city", h, l, r) for h, l, r in zip(
        [19, 21, 24, 29, 33, 35, 36, 35, 33, 30, 25, 20], [9, 10, 12, 15, 19, 22, 23, 23, 21, 18, 14, 10],
        [0.1] * 12)]
    assert cai[6] < 40 and cai[10] > 85 and cai[3] > 70, cai
    bkk = [month_score("tropical", h, l, r) for h, l, r in zip(
        [32, 33, 34, 35, 34, 33, 32, 32, 32, 32, 32, 31], [21, 23, 25, 26, 26, 26, 25, 25, 25, 25, 23, 21],
        [0.3, 0.7, 1.3, 2.5, 5.5, 5.5, 6.0, 7.0, 10.0, 7.0, 2.0, 0.4])]
    assert bkk[0] > 80 and bkk[8] < 35, bkk
    dxb = [month_score("city", h, l, r) for h, l, r in zip(
        [24, 25, 28, 33, 38, 40, 42, 42, 40, 36, 30, 26], [14, 15, 18, 21, 25, 28, 31, 32, 28, 24, 19, 16],
        [0.2] * 12)]
    assert dxb[0] > 90 and dxb[6] < 5, dxb
    print("selftest ok")


def main():
    dests = json.load(open(os.path.join(HERE, "destinations.json"), encoding="utf-8"))
    old = {}
    if os.path.exists(OUT):
        try:
            old = {d["id"]: d for d in json.load(open(OUT, encoding="utf-8")).get("destinations", [])}
        except Exception:
            old = {}
    result, fetched, failed = [], 0, 0
    for dest in dests:
        prev = old.get(dest["id"])
        try:
            need_fetch = "fixed" not in dest and not (prev and prev.get("hi") and prev.get("lat") == dest["lat"] and prev.get("lng") == dest["lng"])
            result.append(build(dest, prev))
            if need_fetch:
                fetched += 1
                time.sleep(0.6)
        except Exception as e:  # keep the old entry if there is one
            failed += 1
            print("failed:", dest["id"], e)
            if prev:
                result.append(prev)
    if not result:
        print("nothing to write")
        sys.exit(1)
    body = {"version": 1, "source": "NASA POWER climate averages", "destinations": result}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    old_text = open(OUT, encoding="utf-8").read() if os.path.exists(OUT) else ""
    if json.loads(old_text or "{}").get("destinations") != result:
        body["generated"] = datetime.date.today().isoformat()
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(body, f, ensure_ascii=False, separators=(",", ":"))
    print("destinations:", len(result), "fetched:", fetched, "failed:", failed)


if __name__ == "__main__":
    selftest() if "--selftest" in sys.argv else main()
