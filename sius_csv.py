"""
SIUS AG CSV parser and summary logic.
Handles semicolon-delimited SIUS export files; summarizes numeric score columns by ID.
"""

from __future__ import annotations

import csv
import io
import math
from pathlib import Path
from collections import defaultdict
from typing import Optional


# SIUS export is typically semicolon-delimited (from SIUSData)
DEFAULT_DELIMITER = ";"

# Common SIUS column names (from SIUSData export / support docs)
SIUS_ID_ALIASES = ("start number", "startnumber", "start_no", "id", "competitor", "shooter")
SIUS_SCORE_ALIASES = ("decimal score", "decimalscore", "score", "decimal", "points", "inner ten", "innerten")


def _normalize_header(name: str) -> str:
    return (name or "").strip().lower().replace(" ", "").replace("_", "").replace("-", "")


def _is_numeric(value: str) -> bool:
    """Return True if value can be parsed as int or float."""
    value = (value or "").strip()
    if not value:
        return False
    try:
        float(value)
        return True
    except ValueError:
        return False


def _parse_value(value: str):
    """Parse string to int if possible, else float, else return original."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        if "." in value or "e" in value.lower():
            return float(value)
        return int(value)
    except ValueError:
        return None


def detect_delimiter(path: Path, sample_size: int = 2) -> str:
    """Guess delimiter from first line(s). Prefer semicolon for SIUS."""
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        first = f.readline()
    return _guess_delimiter_from_first_line(first)


def _guess_delimiter_from_first_line(first_line: str) -> str:
    """Guess delimiter from first line. Prefer semicolon for SIUS."""
    if ";" in first_line and "," not in first_line:
        return ";"
    if "," in first_line:
        return ","
    return DEFAULT_DELIMITER


def load_headers_and_rows(
    path: Path,
    delimiter: Optional[str] = None,
    encoding: str = "utf-8",
) -> tuple[list[str], list[list[str]]]:
    """Load CSV from file; return (headers, rows)."""
    path = Path(path)
    delim = delimiter or detect_delimiter(path)
    with open(path, newline="", encoding=encoding, errors="replace") as f:
        reader = csv.reader(f, delimiter=delim)
        rows = list(reader)
    if not rows:
        return [], []
    headers = [h.strip() for h in rows[0]]
    data_rows = rows[1:]
    return headers, data_rows


def load_headers_and_rows_from_string(
    content: str,
    delimiter: Optional[str] = None,
) -> tuple[list[str], list[list[str]]]:
    """Load CSV from string (e.g. uploaded file); return (headers, rows). First row is treated as header."""
    content = content.strip()
    if not content:
        return [], []
    first_line = content.split("\n")[0] if "\n" in content else content
    delim = delimiter or _guess_delimiter_from_first_line(first_line)
    reader = csv.reader(io.StringIO(content), delimiter=delim)
    rows = list(reader)
    if not rows:
        return [], []
    headers = [h.strip() for h in rows[0]]
    data_rows = rows[1:]
    return headers, data_rows


def load_data_rows_from_string(
    content: str,
    delimiter: Optional[str] = None,
) -> tuple[list[list[str]], str]:
    """
    Load CSV from string with no header row; all rows are data.
    Returns (data_rows, delimiter_used).
    """
    content = content.strip()
    if not content:
        return [], DEFAULT_DELIMITER
    first_line = content.split("\n")[0] if "\n" in content else content
    delim = delimiter or _guess_delimiter_from_first_line(first_line)
    reader = csv.reader(io.StringIO(content), delimiter=delim)
    rows = list(reader)
    if not rows:
        return [], delim
    return rows, delim


def headers_from_field_names(num_columns: int, field_names: list[str]) -> list[str]:
    """
    Build header list for column positions using SIUSFields order.
    field_names[i] is the name for column i; extras are "Column N".
    """
    return [
        field_names[i] if i < len(field_names) else f"Column {i + 1}"
        for i in range(num_columns)
    ]


def infer_column_types(
    headers: list[str],
    rows: list[list[str]],
    id_hint: Optional[str] = None,
    score_hints: Optional[list[str]] = None,
) -> tuple[list[str], list[str]]:
    """
    Infer which column is ID and which are score columns.
    Returns (id_column_names, score_column_names) — each list has 0 or 1 id, and 0+ score names.
    """
    if not headers or not rows:
        return [], []

    normalized = {i: _normalize_header(h) for i, h in enumerate(headers)}
    id_cols = []
    score_cols = []

    # ID: explicit hint or SIUS aliases or first column
    if id_hint:
        for i, h in enumerate(headers):
            if _normalize_header(h) == _normalize_header(id_hint) or id_hint in (h, str(i)):
                id_cols.append(headers[i])
                break
    if not id_cols:
        for i, h in enumerate(headers):
            if normalized[i] in SIUS_ID_ALIASES or "start" in normalized[i]:
                id_cols.append(headers[i])
                break
    if not id_cols:
        id_cols.append(headers[0])

    # Score: explicit hints, SIUS aliases, or any column that is numeric in sample
    score_hint_set = set()
    if score_hints:
        score_hint_set = {_normalize_header(s) for s in score_hints}

    for i, h in enumerate(headers):
        if h in id_cols:
            continue
        if score_hint_set and _normalize_header(h) in score_hint_set:
            score_cols.append(h)
            continue
        if normalized[i] in SIUS_SCORE_ALIASES or "score" in normalized[i] or "decimal" in normalized[i]:
            score_cols.append(h)
            continue
        # Sample first N rows for numeric content
        sample = [row[i] if i < len(row) else "" for row in rows[: min(50, len(rows))]]
        if all(_is_numeric(cell) for cell in sample if cell):
            score_cols.append(h)

    return id_cols, score_cols


def _time_sort_key(time_val: str):
    """Sort key for Time: prefer numeric, else string for HH:MM:SS."""
    v = (time_val or "").strip()
    try:
        return (0, float(v))
    except ValueError:
        return (1, v)


def _column_has_decimals(rows: list[list[str]], col_idx: int) -> bool:
    """Return True if the column contains any value with a fractional part."""
    for row in rows:
        if col_idx >= len(row):
            continue
        v = (row[col_idx] or "").strip()
        if not v:
            continue
        try:
            f = float(v)
            if f != int(f):
                return True
        except ValueError:
            pass
    return False


def _decimal_and_integer_scores(
    primary_val: Optional[float],
    secondary_val: Optional[float],
    primary_is_decimal: bool,
) -> tuple[Optional[float], Optional[int]]:
    """
    Derive decimal_score and integer_score from Primary and Secondary.
    If Primary is decimal and Secondary is 0, integer = floor(Primary).
    """
    if primary_is_decimal:
        decimal_val = primary_val
        if secondary_val is not None and secondary_val != 0:
            integer_val = int(secondary_val)
        elif primary_val is not None:
            integer_val = math.floor(primary_val)
        else:
            integer_val = None
    else:
        integer_val = int(primary_val) if primary_val is not None else None
        decimal_val = secondary_val
    return (decimal_val, integer_val)


def summarize_decimal_integer(
    headers: list[str],
    rows: list[list[str]],
    id_column: str,
    primary_column: str,
    secondary_column: Optional[str],
) -> list[dict]:
    """
    Group by ID and aggregate Decimal score and Integer score.
    Decimal/Integer are derived from Primary and Secondary: the column with decimals is Decimal,
    the other is Integer. When Primary is decimal and Secondary is 0, Integer = floor(Primary).
    Returns list of dicts: { "id", "count", "Decimal score_sum", "Decimal score_mean",
    "Integer score_sum", "Integer score_mean" }.
    """
    id_idx = next((i for i, h in enumerate(headers) if h == id_column), None)
    primary_idx = next((i for i, h in enumerate(headers) if h == primary_column), None)
    secondary_idx = next((i for i, h in enumerate(headers) if h == secondary_column), None) if secondary_column else None
    if id_idx is None or primary_idx is None:
        return []
    primary_is_decimal = _column_has_decimals(rows, primary_idx)

    by_id = defaultdict(lambda: {"count": 0, "decimal_sum": 0.0, "decimal_n": 0, "integer_sum": 0, "integer_n": 0})

    for row in rows:
        if id_idx >= len(row):
            continue
        id_val = (row[id_idx] or "").strip()
        if not id_val:
            continue
        primary_val = _parse_value(row[primary_idx]) if primary_idx is not None and primary_idx < len(row) else None
        secondary_val = _parse_value(row[secondary_idx]) if secondary_idx is not None and secondary_idx < len(row) else None
        decimal_score, integer_score = _decimal_and_integer_scores(
            primary_val, secondary_val, primary_is_decimal
        )
        by_id[id_val]["count"] += 1
        if decimal_score is not None:
            by_id[id_val]["decimal_sum"] += decimal_score
            by_id[id_val]["decimal_n"] += 1
        if integer_score is not None:
            by_id[id_val]["integer_sum"] += integer_score
            by_id[id_val]["integer_n"] += 1

    result = []
    for id_val in sorted(by_id.keys(), key=lambda x: (str(x).isdigit(), str(x).zfill(10) if str(x).isdigit() else x)):
        rec = by_id[id_val]
        out = {
            "id": id_val,
            "count": rec["count"],
            "Decimal score_sum": round(rec["decimal_sum"], 4) if rec["decimal_n"] else None,
            "Decimal score_mean": round(rec["decimal_sum"] / rec["decimal_n"], 4) if rec["decimal_n"] else None,
            "Integer score_sum": rec["integer_sum"] if rec["integer_n"] else None,
            "Integer score_mean": round(rec["integer_sum"] / rec["integer_n"], 4) if rec["integer_n"] else None,
        }
        result.append(out)
    return result


def get_shots_for_start_nr(
    headers: list[str],
    rows: list[list[str]],
    id_column: str,
    primary_column: str,
    secondary_column: Optional[str],
    time_column: str,
    start_nr_val: str,
) -> list[dict]:
    """
    Return list of shots for the given Start NR from rows (already filtered by relay/start_nrs).
    Each shot has: index (in rows), Time, Primary score, Secondary score, Decimal score, Integer score.
    Sorted descending by Time (newest first).
    """
    id_idx = next((i for i, h in enumerate(headers) if h == id_column), None)
    primary_idx = next((i for i, h in enumerate(headers) if h == primary_column), None)
    secondary_idx = next((i for i, h in enumerate(headers) if h == secondary_column), None) if secondary_column else None
    time_idx = next((i for i, h in enumerate(headers) if h == time_column), None)
    if id_idx is None or primary_idx is None:
        return []
    primary_is_decimal = _column_has_decimals(rows, primary_idx)
    start_nr_val = str(start_nr_val).strip()
    shots = []
    for idx, row in enumerate(rows):
        if id_idx >= len(row) or (row[id_idx] or "").strip() != start_nr_val:
            continue
        primary_val = _parse_value(row[primary_idx]) if primary_idx < len(row) else None
        secondary_val = _parse_value(row[secondary_idx]) if secondary_idx is not None and secondary_idx < len(row) else None
        decimal_score, integer_score = _decimal_and_integer_scores(
            primary_val, secondary_val, primary_is_decimal
        )
        time_val = row[time_idx].strip() if time_idx is not None and time_idx < len(row) else ""
        primary_str = str(primary_val) if primary_val is not None else ""
        secondary_str = str(secondary_val) if secondary_val is not None else ""
        shots.append({
            "index": idx,
            "Time": time_val,
            "Primary score": primary_str,
            "Secondary score": secondary_str,
            "Decimal score": round(decimal_score, 4) if decimal_score is not None else None,
            "Integer score": integer_score,
        })
    shots.sort(key=lambda s: _time_sort_key(s["Time"]), reverse=True)
    return shots


def summarize_by_id(
    headers: list[str],
    rows: list[list[str]],
    id_column: str,
    score_columns: list[str],
) -> list[dict]:
    """
    Group rows by ID column and aggregate score columns (sum, count, mean).
    Returns list of dicts: { "id", "count", "<score_col>_sum", "<score_col>_mean", ... }.
    """
    id_idx = next((i for i, h in enumerate(headers) if h == id_column), None)
    if id_idx is None:
        return []

    score_idxs = [(i, h) for i, h in enumerate(headers) if h in score_columns]
    if not score_idxs:
        return []

    by_id = defaultdict(lambda: {"count": 0, "sums": {h: 0.0 for _, h in score_idxs}, "values": {h: [] for _, h in score_idxs}})

    for row in rows:
        if id_idx >= len(row):
            continue
        id_val = (row[id_idx] or "").strip()
        if not id_val:
            continue
        by_id[id_val]["count"] += 1
        for col_i, col_name in score_idxs:
            v = _parse_value(row[col_i]) if col_i < len(row) else None
            if v is not None:
                by_id[id_val]["sums"][col_name] += v
                by_id[id_val]["values"][col_name].append(v)

    result = []
    for id_val in sorted(by_id.keys(), key=lambda x: (str(x).isdigit(), str(x).zfill(10) if str(x).isdigit() else x)):
        rec = by_id[id_val]
        out = {"id": id_val, "count": rec["count"]}
        for col_name in score_columns:
            s = rec["sums"][col_name]
            n = len(rec["values"][col_name])
            out[f"{col_name}_sum"] = round(s, 4)
            out[f"{col_name}_mean"] = round(s / n, 4) if n else None
        result.append(out)
    return result
