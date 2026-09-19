"""Read data files of many formats into (rows, columns)."""
import csv
import json
import sqlite3
from pathlib import Path

SUPPORTED_EXTS = (".csv", ".tsv", ".json", ".jsonl", ".ndjson",
                  ".parquet", ".pq", ".xlsx", ".xls", ".db", ".sqlite",
                  ".sqlite3")

FILE_FILTER = (
    "Training data (*.csv *.tsv *.json *.jsonl *.ndjson "
    "*.parquet *.pq *.xlsx *.xls *.db *.sqlite *.sqlite3);;All files (*)"
)


def _detect_delimiter(sample):
    counts = {
        ",": sample.count(","),
        "\t": sample.count("\t"),
        ";": sample.count(";"),
        "|": sample.count("|"),
    }
    top = max(counts, key=counts.get)
    return top if counts[top] > 0 else ","


def load_csv(path, delimiter=None):
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        if delimiter is None:
            sample = f.read(65536)
            f.seek(0)
            delimiter = _detect_delimiter(sample)
        reader = csv.DictReader(f, delimiter=delimiter)
        rows = [dict(r) for r in reader]
        cols = list(reader.fieldnames or [])
    return rows, cols


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        # {"examples": [...]} or {"data": [...]}
        for key in ("examples", "data", "rows", "items"):
            if key in data and isinstance(data[key], list):
                data = data[key]
                break
        else:
            # single dict → one-row table
            data = [data]
    if not isinstance(data, list) or not data:
        raise ValueError("JSON has no list of objects")
    cols = []
    for r in data:
        if isinstance(r, dict):
            for k in r.keys():  # noqa: SIM118
                if k not in cols:
                    cols.append(k)
    rows = [r for r in data if isinstance(r, dict)]
    return rows, cols


def load_jsonl(path):
    rows, cols = [], []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            for k in obj.keys():
                if k not in cols:
                    cols.append(k)
            rows.append(obj)
    return rows, cols


def load_parquet(path):
    try:
        import pyarrow.parquet as pq
    except ImportError:
        try:
            import pandas as pd
            df = pd.read_parquet(path)
            return df.to_dict("records"), list(df.columns)
        except ImportError:
            raise ImportError(
                "Parquet support requires pyarrow or pandas.\n"
                "Install with:  pip3 install --user pyarrow")
    table = pq.read_table(str(path))
    rows = table.to_pylist()
    cols = list(table.column_names)
    return rows, cols


def load_excel(path):
    try:
        import openpyxl
    except ImportError:
        try:
            import pandas as pd
            df = pd.read_excel(path)
            return df.to_dict("records"), list(df.columns)
        except ImportError:
            raise ImportError(
                "Excel support requires openpyxl or pandas.\n"
                "Install with:  pip3 install --user openpyxl")
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    header = None
    rows = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            header = [str(c) if c is not None else f"col_{j}"
                      for j, c in enumerate(row)]
            continue
        rows.append({header[j]: row[j] for j in range(len(header))})
    wb.close()
    return rows, header or []


def load_sqlite(path, table=None):
    conn = sqlite3.connect(str(path))
    cur = conn.cursor()
    if not table:
        cur.execute("SELECT name FROM sqlite_master "
                    "WHERE type='table' ORDER BY name")
        tables = [r[0] for r in cur.fetchall()]
        if not tables:
            conn.close()
            raise ValueError("SQLite file has no tables")
        table = tables[0]
    cur.execute(f'SELECT * FROM "{table}"')
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()
    return rows, cols


def load_file(path, table=None):
    """Dispatch by extension. Returns (rows, columns)."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(str(p))
    ext = p.suffix.lower()
    if ext == ".csv":    return load_csv(p, ",")
    if ext == ".tsv":    return load_csv(p, "\t")
    if ext == ".json":   return load_json(p)
    if ext in (".jsonl", ".ndjson"): return load_jsonl(p)
    if ext in (".parquet", ".pq"):   return load_parquet(p)
    if ext in (".xlsx", ".xls"):     return load_excel(p)
    if ext in (".db", ".sqlite", ".sqlite3"): return load_sqlite(p, table)
    # unknown → try CSV as last resort
    return load_csv(p, ",")