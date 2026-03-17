#!/usr/bin/env python3
"""
Count events per city and per category from a TTL file (rdflib).
Usage:
  python3 scripts/count_events_by_city.py --input mixed-events.ttl --out-dir out/

Writes:
  - out/event_counts_by_city.csv
  - out/event_counts_summary.json
"""
from pathlib import Path
import argparse
import csv
import json
from collections import Counter

from rdflib import Graph, Namespace, RDF, URIRef, Literal

SCHEMA = Namespace("http://schema.org/")


def get_literal_str(g: Graph, subj, pred):
    v = g.value(subj, pred)
    if isinstance(v, Literal):
        return str(v)
    if isinstance(v, URIRef):
        return str(v)
    return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", "-i", required=True, help="Input TTL file")
    p.add_argument("--out-dir", "-o", default="out", help="Output directory")
    args = p.parse_args()

    g = Graph()
    g.parse(args.input, format="turtle")

    counts = Counter()            # (city_label, category) -> count
    per_city = Counter()          # city_label -> total events
    per_category = Counter()      # category -> total events

    # iterate over CreativeWork subjects
    for s in set(g.subjects(RDF.type, SCHEMA.CreativeWork)):
        city_label = get_literal_str(g, s, SCHEMA.cityLabel)
        # fallback: try schema:city (URI) then use last path segment or fragment
        if not city_label:
            city_ref = g.value(s, SCHEMA.city)
            if isinstance(city_ref, URIRef):
                uri = str(city_ref)
                if "#" in uri:
                    city_label = uri.split("#")[-1]
                else:
                    city_label = uri.rstrip("/").split("/")[-1]
        if not city_label:
            city_label = "UNKNOWN"

        category = get_literal_str(g, s, SCHEMA.category) or "UNKNOWN"

        counts[(city_label, category)] += 1
        per_city[city_label] += 1
        per_category[category] += 1

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # CSV: city,category,count
    csv_path = out_dir / "event_counts_by_city.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["city", "category", "count"])
        for (city, cat), c in sorted(counts.items(), key=lambda x: (x[0][0].lower(), x[0][1].lower())):
            writer.writerow([city, cat, c])

    # JSON summary: per city and per category
    summary = {
        "by_city_and_category": {},
        "totals": {
            "per_city": dict(per_city),
            "per_category": dict(per_category),
            "total_events": sum(per_city.values())
        }
    }
    # build nested dict
    cities = sorted({c for (c, _) in counts.keys()})
    for city in cities:
        cats = {cat: cnt for (c, cat), cnt in counts.items() if c == city}
        summary["by_city_and_category"][city] = cats

    json_path = out_dir / "event_counts_summary.json"
    with json_path.open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False)

    # Print concise table
    print(f"Parsed {args.input}")
    print(f"Total events: {summary['totals']['total_events']}")
    print("\nEvents per city (total):")
    for city, cnt in per_city.most_common():
        print(f"  {city}: {cnt}")
    print("\nTop categories overall:")
    for cat, cnt in per_category.most_common(10):
        print(f"  {cat}: {cnt}")

    print(f"\nCSV written to: {csv_path}")
    print(f"JSON summary written to: {json_path}")


if __name__ == "__main__":
    main()
