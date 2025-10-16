"""
CSV → JSON transformer (Aggregator 1: group by energy series)

Turns a "wide" monthly time-series CSV into an array of grouped series
objects shaped like:

  {
    "group": "Energy Production",
    "series": "Crude Oil Production",
    "unit": "million barrels per day",
    "source_key": "COPRPUS",
    "data": [
      {"date": "1999-10", "value": 5.95},
      {"date": "1999-11", "value": 5.88}
    ]
  }

Run patterns:
- Import and call: records = transform_csv_to_json(csv_text)
- CLI (stdout): python energy_aggregator_1.py input.csv > energy_llm.json
- CLI (file):   python energy_aggregator_1.py input.csv -o energy_llm.json
"""
from __future__ import annotations

import csv
import io
import json
import re
from typing import List, Dict, Optional

MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}

# --- Date header parsing -----------------------------------------------------

def _parse_header_date(tok: str) -> Optional[str]:
    tok = tok.strip()
    if not tok:
        return None
    # Pattern A: "Jan-97"
    m = re.match(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)-(\d{2})$", tok)
    if m:
        mon = MONTHS[m.group(1)]
        yy = int(m.group(2))
        # Map >=90 to 1900s, else 2000s (handles 97..00 range in your sheet)
        year = 1900 + yy if yy >= 90 else 2000 + yy
        return f"{year:04d}-{mon:02d}"
    # Pattern B: "1-Jan" → 2001‑01, "26-Dec" → 2026‑12
    m = re.match(r"^(\d{1,2})-(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)$", tok)
    if m:
        yoff = int(m.group(1))
        mon = MONTHS[m.group(2)]
        year = 2000 + yoff
        return f"{year:04d}-{mon:02d}"
    return None


# --- Transform ---------------------------------------------------------------

def transform_csv_to_json(csv_text: str) -> List[Dict]:
    reader = csv.reader(io.StringIO(csv_text))
    try:
        header = next(reader)
    except StopIteration:
        return []

    # Find the important header columns dynamically
    def _norm(x: str) -> str:
        return (x or "").strip().lower().replace(" ", "")

    units_idx = next((i for i, h in enumerate(header) if _norm(h) == "units"), None)
    src_idx = next((i for i, h in enumerate(header) if _norm(h) in ("sourcekey", "source_key")), None)

    if units_idx is None or src_idx is None:
        raise ValueError("Could not locate 'units' and 'source key' in header.")

    group_idx, series_idx = 0, 1

    # Build date vector from header tail
    date_headers = header[src_idx + 1:]
    date_keys = [_parse_header_date(tok) for tok in date_headers]

    out: List[Dict] = []

    for row in reader:
        if len(row) <= src_idx:
            continue
        group = (row[group_idx] if len(row) > group_idx else "").strip()
        series = (row[series_idx] if len(row) > series_idx else "").strip()
        units = (row[units_idx] if len(row) > units_idx else "").strip()
        source_key = (row[src_idx] if len(row) > src_idx else "").strip()

        # Skip headers/blank lines with no concrete series
        if not series or not units or not source_key:
            continue

        values = row[src_idx + 1:]
        if len(values) < len(date_keys):
            values = values + [""] * (len(date_keys) - len(values))
        elif len(values) > len(date_keys):
            values = values[:len(date_keys)]

        data_points = []
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
            data_points.append({"date": dkey, "value": num})

        # Only emit a series object if we have at least one numeric data point
        if data_points:
            out.append({
                "group": group,
                "series": series,
                "unit": units,
                "source_key": source_key,
                "data": data_points,
            })
    return out


# --- Optional helper for simple Q&A over the transformed JSON ----------------

def lookup_value(records: List[Dict], series_contains: str, year: int, month: int) -> Optional[Dict]:
    series_contains = series_contains.lower()
    target_date = f"{year:04d}-{month:02d}"
    for series_obj in records:
        if series_contains not in series_obj.get("series", "").lower():
            continue
        for dp in series_obj.get("data", []):
            if dp.get("date") == target_date:
                return {
                    "group": series_obj.get("group"),
                    "series": series_obj.get("series"),
                    "unit": series_obj.get("unit"),
                    "source_key": series_obj.get("source_key"),
                    "date": dp.get("date"),
                    "value": dp.get("value"),
                }
    return None


if __name__ == "__main__":
    import argparse, sys
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="Path to input CSV (wide format)")
    ap.add_argument("-o", "--output", default="-", help="Path to output JSON file (use '-' for stdout)")
    args = ap.parse_args()
    with open(args.input, "r", encoding="utf-8") as f:
        csv_text = f.read()
    records = transform_csv_to_json(csv_text)
    if args.output in ("-", "", None):
        json.dump(records, sys.stdout, ensure_ascii=False, separators=(",", ":"))
    else:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, separators=(",", ":"))


