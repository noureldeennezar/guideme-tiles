#!/usr/bin/env python3
"""
build_events.py - builds events/events.json for the GuideMe app from Wikidata
(free, worldwide, no API key).

Accuracy rules (the same as the app):
  * only events with an EXACT day (Wikidata time precision = day or better),
  * only events that have coordinates,
  * only events that have an English name (never a bare "Q12345"),
  * a photo only if Wikidata itself holds one for that event/place (Wikimedia Commons).
Anything vaguer is skipped, never guessed.

Usage (from the project folder, Python 3 only, no packages):
    python scripts/build_events.py --out ../guideme-tiles/events/events.json
    python scripts/build_events.py --selftest        # checks the converter, no internet

Then push the guideme-tiles repo like you do for tiles (Cloudflare republishes it).
The app reads  <TILES_BASE_URL>/events/events.json.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

ENDPOINT = "https://query.wikidata.org/sparql"
UA = "GuideMe-events-builder/1.0 (https://github.com; travel discovery app)"
DAYS_AHEAD = 400

# kind -> Wikidata classes (subclasses are included automatically)
EVENT_TYPES = {
    "festival": ["Q132241", "Q868557", "Q220505"],  # festival, music festival, film festival
    "concert": ["Q182832"],                          # concert
    "exhibition": ["Q464980"],                       # exhibition
    "sport": ["Q16510064"],                          # sporting event
}


def run_query(query, retries=4):
    url = ENDPOINT + "?" + urllib.parse.urlencode({"query": query, "format": "json"})
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/sparql-results+json"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read().decode("utf-8"))["results"]["bindings"]
        except Exception as e:  # network, 429, 504 ...
            last = e
            time.sleep(5 * (attempt + 1))
    print("  query failed: %s" % last, file=sys.stderr)
    return []


def window():
    today = dt.datetime.now(dt.timezone.utc).date()
    end = today + dt.timedelta(days=DAYS_AHEAD)
    return today.isoformat() + "T00:00:00Z", end.isoformat() + "T00:00:00Z"


def opening_query():
    a, b = window()
    return """
SELECT ?item ?itemLabel ?date ?prec ?coord ?image ?countryLabel ?locLabel ?site WHERE {
  ?item p:P1619 ?st .
  ?st psv:P1619 ?v .
  ?v wikibase:timeValue ?date ; wikibase:timePrecision ?prec .
  FILTER(?prec >= 11 && ?date >= "%s"^^xsd:dateTime && ?date <= "%s"^^xsd:dateTime)
  ?item wdt:P625 ?coord .
  OPTIONAL { ?item wdt:P18 ?image }
  OPTIONAL { ?item wdt:P17 ?country }
  OPTIONAL { ?item wdt:P131 ?loc }
  OPTIONAL { ?item wdt:P856 ?site }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,mul". }
} LIMIT 3000
""" % (a, b)


def event_query(classes):
    a, b = window()
    values = " ".join("wd:" + c for c in classes)
    return """
SELECT ?item ?itemLabel ?date ?prec ?endDate ?endPrec ?coord ?image ?countryLabel ?locLabel ?venueLabel ?site WHERE {
  VALUES ?type { %s }
  ?item wdt:P31/wdt:P279* ?type .
  ?item p:P580 ?st .
  ?st psv:P580 ?v .
  ?v wikibase:timeValue ?date ; wikibase:timePrecision ?prec .
  FILTER(?prec >= 11 && ?date >= "%s"^^xsd:dateTime && ?date <= "%s"^^xsd:dateTime)
  OPTIONAL { ?item wdt:P625 ?c1 }
  OPTIONAL { ?item wdt:P276 ?venue . ?venue wdt:P625 ?c2 }
  BIND(COALESCE(?c1, ?c2) AS ?coord)
  FILTER(BOUND(?coord))
  OPTIONAL { ?item p:P582 ?en . ?en psv:P582 ?ev . ?ev wikibase:timeValue ?endDate ; wikibase:timePrecision ?endPrec }
  OPTIONAL { ?item wdt:P18 ?image }
  OPTIONAL { ?item wdt:P17 ?country }
  OPTIONAL { ?item wdt:P131 ?loc }
  OPTIONAL { ?item wdt:P856 ?site }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,mul". }
} LIMIT 2000
""" % (values, a, b)


def val(row, key):
    v = row.get(key)
    return v["value"] if v else None


def parse_point(wkt):
    m = re.match(r"Point\(\s*(-?[\d.eE+-]+)\s+(-?[\d.eE+-]+)\s*\)", wkt or "")
    if not m:
        return None
    lng, lat = float(m.group(1)), float(m.group(2))
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None
    return lat, lng


def day_of(iso):
    # Wikidata gives 2026-12-25T00:00:00Z (or with a leading +)
    d = (iso or "").lstrip("+")[:10]
    try:
        return dt.date.fromisoformat(d)
    except ValueError:
        return None


def commons_image(url):
    """Special:FilePath links -> a sized https link (verified Wikimedia photo)."""
    if not url:
        return None
    u = url.replace("http://", "https://", 1)
    if "Special:FilePath" not in u:
        return None
    return u + ("&" if "?" in u else "?") + "width=900"


def good_label(label, qid):
    if not label:
        return False
    if re.fullmatch(r"Q\d+", label.strip()):
        return False
    return len(label.strip()) >= 3


def rows_to_events(rows, kind):
    out = []
    for r in rows:
        item = val(r, "item") or ""
        qid = item.rsplit("/", 1)[-1]
        label = (val(r, "itemLabel") or "").strip()
        if not qid.startswith("Q") or not good_label(label, qid):
            continue
        if int(float(val(r, "prec") or 0)) < 11:
            continue
        start = day_of(val(r, "date"))
        pt = parse_point(val(r, "coord"))
        if start is None or pt is None:
            continue
        end = None
        if val(r, "endDate") and int(float(val(r, "endPrec") or 0)) >= 11:
            e = day_of(val(r, "endDate"))
            if e and e >= start and (e - start).days <= 60:
                end = e
        site = val(r, "site")
        src = site if site and site.startswith("http") else "https://www.wikidata.org/wiki/" + qid
        loc = (val(r, "locLabel") or "").strip()
        venue = (val(r, "venueLabel") or "").strip()
        country = (val(r, "countryLabel") or "").strip()
        place = venue if (venue and not re.fullmatch(r"Q\d+", venue)) else ""
        if re.fullmatch(r"Q\d+", loc):
            loc = ""
        if re.fullmatch(r"Q\d+", country):
            country = ""
        ev = {
            "id": "wd_" + qid,
            "title": label,
            "kind": kind,
            "start": start.isoformat() + "T00:00:00.000Z",
            "allDay": True,
            "lat": round(pt[0], 5),
            "lng": round(pt[1], 5),
            "place": place if kind != "opening" else "",
            "city": loc,
            "country": country,
            "about": "",
            "sourceName": "Wikidata",
            "sourceUrl": src,
            "origin": "official",
            "reports": 0,
        }
        if end:
            ev["end"] = end.isoformat() + "T00:00:00.000Z"
        img = commons_image(val(r, "image"))
        if img:
            ev["image"] = img
        out.append(ev)
    return out


def merge(events):
    seen, out = set(), []
    for e in sorted(events, key=lambda x: (x["start"], x["title"].lower())):
        if e["id"] in seen:
            continue
        seen.add(e["id"])
        out.append(e)
    return out


def build():
    events = []
    print("openings ...")
    events += rows_to_events(run_query(opening_query()), "opening")
    for kind, classes in EVENT_TYPES.items():
        print("%s ..." % kind)
        events += rows_to_events(run_query(event_query(classes)), kind)
        time.sleep(2)
    return merge(events)


def selftest():
    sample = [
        {"item": {"value": "http://www.wikidata.org/entity/Q1"}, "itemLabel": {"value": "Grand Test Museum"},
         "date": {"value": "2026-12-25T00:00:00Z"}, "prec": {"value": "11"},
         "coord": {"value": "Point(31.1178 29.9942)"},
         "image": {"value": "http://commons.wikimedia.org/wiki/Special:FilePath/Test.jpg"},
         "countryLabel": {"value": "Egypt"}, "locLabel": {"value": "Giza"}},
        {"item": {"value": "http://www.wikidata.org/entity/Q2"}, "itemLabel": {"value": "Q2"},
         "date": {"value": "2026-12-25T00:00:00Z"}, "prec": {"value": "11"}, "coord": {"value": "Point(1 1)"}},
        {"item": {"value": "http://www.wikidata.org/entity/Q3"}, "itemLabel": {"value": "Only a month"},
         "date": {"value": "2026-12-01T00:00:00Z"}, "prec": {"value": "10"}, "coord": {"value": "Point(1 1)"}},
        {"item": {"value": "http://www.wikidata.org/entity/Q4"}, "itemLabel": {"value": "No coordinates"},
         "date": {"value": "2026-12-01T00:00:00Z"}, "prec": {"value": "11"}},
        {"item": {"value": "http://www.wikidata.org/entity/Q5"}, "itemLabel": {"value": "Film Fest"},
         "date": {"value": "2026-11-20T00:00:00Z"}, "prec": {"value": "11"},
         "endDate": {"value": "2026-11-29T00:00:00Z"}, "endPrec": {"value": "11"},
         "coord": {"value": "Point(31.2 30.0)"}, "site": {"value": "https://example.org"},
         "venueLabel": {"value": "Cairo Opera House"}},
    ]
    ev = merge(rows_to_events(sample, "festival") + rows_to_events(sample[:1], "festival"))
    assert [e["id"] for e in ev] == ["wd_Q5", "wd_Q1"], ev
    assert ev[1]["image"].endswith("Test.jpg?width=900")
    assert ev[1]["lat"] == 29.9942 and ev[1]["lng"] == 31.1178
    assert ev[0]["end"].startswith("2026-11-29") and ev[0]["place"] == "Cairo Opera House"
    assert ev[0]["sourceUrl"] == "https://example.org"
    assert ev[1]["sourceUrl"].endswith("/Q1")
    q = event_query(["Q132241"])
    assert "wd:Q132241" in q and "P580" in q
    print("selftest OK (%d events kept of %d rows)" % (len(ev), len(sample)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="events/events.json")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
        return
    events = build()
    if not events:
        print("No events found (network problem?). Keeping the old file.", file=sys.stderr)
        sys.exit(1)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    doc = {"v": 1, "generated": dt.datetime.now(dt.timezone.utc).isoformat(), "events": events}
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    print("wrote %d events -> %s" % (len(events), a.out))


if __name__ == "__main__":
    main()
