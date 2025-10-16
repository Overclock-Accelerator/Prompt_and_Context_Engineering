## Energy CSV → JSON Converter

This folder contains a small utility to convert a "wide" monthly time-series CSV into a JSON format optimized for LLM use.

### Requirements
- Python 3.8+ (standard library only)

### Files
- `energy_aggregator_1.py`: Aggregates by energy series (group → series → data points)
- `energy_aggregator_2.py`: Aggregates by date (date → series values for that month)
- `01-Energy_Original.csv`: Original raw CSV (for reference)
- `02-Energy_Reformatted.csv`: Reformatted/wide CSV (use this as input)
- `03-Energy_LLM_Format.json`: Example output JSON file

### Execution (CLI)
You can write JSON to stdout (redirect to a file), or directly to a file with `-o`.

- Aggregator 1 (by series) — Option A: stdout → redirect to destination file
```bash
python energy_aggregator_1.py 02-Energy_Reformatted.csv > 03-Energy_LLM_Format.json
```

- Aggregator 1 (by series) — Option B: write directly to a file with -o
```bash
python energy_aggregator_1.py 02-Energy_Reformatted.csv -o 03-Energy_LLM_Format.json
```

- Aggregator 2 (by date) — stdout → redirect to destination file
```bash
python energy_aggregator_2.py 02-Energy_Reformatted.csv > 03-Energy_By_Date.json
```

- Aggregator 2 (by date) — write directly to a file with -o
```bash
python energy_aggregator_2.py 02-Energy_Reformatted.csv -o 03-Energy_By_Date.json
```

Notes:
- By default, output goes to stdout. Using `-o path.json` writes to that file.
- The script does not print the output path; it only emits the JSON (stdout) or writes the JSON to the specified file.

### Output formats

- Aggregator 1 (by series): array of series objects, each with a `data` array of `{date, value}` pairs:
```json
[
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
]
```

- Aggregator 2 (by date): array of date objects, each with a `data` array of series values for that month:
```json
[
  {
    "date": "1999-10",
    "data": [
      {"group": "Energy Production", "series": "Crude Oil Production", "unit": "million barrels per day", "source_key": "COPRPUS", "value": 5.95}
    ]
  }
]
```

### Programmatic use (import)
```python
from energy_aggregator_1 import transform_csv_to_json

with open("02-Energy_Reformatted.csv", "r", encoding="utf-8") as f:
    csv_text = f.read()

records = transform_csv_to_json(csv_text)
print(len(records))
print(records[0])
```

For date aggregation programmatic use:
```python
from energy_aggregator_2 import transform_csv_to_json_by_date

with open("02-Energy_Reformatted.csv", "r", encoding="utf-8") as f:
    csv_text = f.read()

records = transform_csv_to_json_by_date(csv_text)
print(len(records))
print(records[0])
```


