"""
CSV → JSON transformer (Aggregator 2: group by date)

Turns a "wide" monthly time-series CSV into an array of date buckets
shaped like:

  {
    "date": "1999-10",
    "data": [
      {"group": "Energy Production", "series": "Crude Oil Production", "unit": "million barrels per day", "source_key": "COPRPUS", "value": 5.95},
      {"group": "Energy Production", "series": "Natural Gas Production", "unit": "billion cubic feet", "source_key": "NGPRPUS", "value": 1680.1}
    ]
  }

Run patterns:
- Import and call: records = transform_csv_to_json_by_date(csv_text)
- CLI (stdout): python energy_aggregator_2.py input.csv > energy_by_date.json
- CLI (file):   python energy_aggregator_2.py input.csv -o energy_by_date.json
"""
from __future__ import annotations

import csv
import io
import json
import re
from typing import Dict, List, Optional

MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}


def _parse_header_date(tok: str) -> Optional[str]:
    tok = tok.strip()
    if not tok:
        return None
    m = re.match(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)-(\d{2})$", tok)
    if m:
        mon = MONTHS[m.group(1)]
        yy = int(m.group(2))
        year = 1900 + yy if yy >= 90 else 2000 + yy
        return f"{year:04d}-{mon:02d}"
    m = re.match(r"^(\d{1,2})-(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)$", tok)
    if m:
        yoff = int(m.group(1))
        mon = MONTHS[m.group(2)]
        year = 2000 + yoff
        return f"{year:04d}-{mon:02d}"
    return None


def _unique_in_order(seq: List[Optional[str]]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for x in seq:
        if not x:
            continue
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def transform_csv_to_json_by_date(csv_text: str) -> List[Dict]:
    reader = csv.reader(io.StringIO(csv_text))
    try:
        header = next(reader)
    except StopIteration:
        return []

    def _norm(x: str) -> str:
        return (x or "").strip().lower().replace(" ", "")

    units_idx = next((i for i, h in enumerate(header) if _norm(h) == "units"), None)
    src_idx = next((i for i, h in enumerate(header) if _norm(h) in ("sourcekey", "source_key")), None)

    if units_idx is None or src_idx is None:
        raise ValueError("Could not locate 'units' and 'source key' in header.")

    group_idx, series_idx = 0, 1

    date_headers = header[src_idx + 1:]
    date_keys = [_parse_header_date(tok) for tok in date_headers]
    ordered_dates = _unique_in_order(date_keys)

    buckets: Dict[str, List[Dict]] = {d: [] for d in ordered_dates}

    for row in reader:
        if len(row) <= src_idx:
            continue
        group = (row[group_idx] if len(row) > group_idx else "").strip()
        series = (row[series_idx] if len(row) > series_idx else "").strip()
        units = (row[units_idx] if len(row) > units_idx else "").strip()
        source_key = (row[src_idx] if len(row) > src_idx else "").strip()

        if not series or not units or not source_key:
            continue

        values = row[src_idx + 1:]
        if len(values) < len(date_keys):
            values = values + [""] * (len(date_keys) - len(values))
        elif len(values) > len(date_keys):
            values = values[:len(date_keys)]

        for dkey, val in zip(date_keys, values):
            if not dkey:
                continue
            v = (val or "").strip()
            if not v or v == "--":
                continue
            try:
                num = float(v)
            except ValueError:
                continue
            buckets[dkey].append({
                "group": group,
                "series": series,
                "unit": units,
                "source_key": source_key,
                "value": num,
            })

    out: List[Dict] = []
    for d in ordered_dates:
        data_list = buckets.get(d, [])
        if not data_list:
            continue
        out.append({"date": d, "data": data_list})
    return out


if __name__ == "__main__":
    import argparse, sys
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="Path to input CSV (wide format)")
    ap.add_argument("-o", "--output", default="-", help="Path to output JSON file (use '-' for stdout)")
    args = ap.parse_args()
    with open(args.input, "r", encoding="utf-8") as f:
        csv_text = f.read()
    records = transform_csv_to_json_by_date(csv_text)
    if args.output in ("-", "", None):
        json.dump(records, sys.stdout, ensure_ascii=False, separators=(",", ":"))
    else:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, separators=(",", ":"))


