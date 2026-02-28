"""
Load SIUSFields.txt (tab-separated) and match CSV column names to SIUS field names.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional

# Standard SIUS field names we use (from SIUSFields.txt first column)
START_NR = "Start NR"
PRIMARY_SCORE = "Primary score"
SECONDARY_SCORE = "Secondary score"

# First column header in SIUSFields.txt (may be "Field" or "Fields")
FIELD_COLUMN_HEADER = "Field"


def _normalize(name: str) -> str:
    return (name or "").strip().lower().replace(" ", "").replace("_", "").replace("-", "")


def load_field_names(path: Path) -> list[str]:
    """
    Load SIUSFields.txt (tab-separated, header row).
    Return list of field names from the first column (header row excluded).
    """
    path = Path(path)
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f, delimiter="\t")
        rows = list(reader)
    if not rows:
        return []
    # First row is header; first column is "Field" or "Fields"
    headers = [h.strip() for h in rows[0]]
    if not headers:
        return []
    field_col_idx = 0
    for i, h in enumerate(headers):
        if _normalize(h) in ("field", "fields"):
            field_col_idx = i
            break
    names = []
    for row in rows[1:]:
        if field_col_idx < len(row) and row[field_col_idx].strip():
            names.append(row[field_col_idx].strip())
    return names


# Aliases: CSV header patterns that map to SIUS field names (normalized)
START_NR_ALIASES = ("startnr", "startnumber", "start_no", "startno")
PRIMARY_SCORE_ALIASES = ("primaryscore", "decimalscore", "decimal score", "primary score")
SECONDARY_SCORE_ALIASES = ("secondaryscore", "secondary score")


def match_csv_header_to_field(csv_headers: list[str], target_field: str) -> Optional[str]:
    """
    Find a CSV header that matches the given SIUS field name (case-insensitive, ignore spaces/underscores).
    Returns the actual CSV header string if found, else None.
    """
    target_norm = _normalize(target_field)
    for h in csv_headers:
        if _normalize(h) == target_norm:
            return h
    # Start NR: e.g. "Start number" in older SIUS exports
    if target_norm == _normalize(START_NR):
        for h in csv_headers:
            if _normalize(h) in START_NR_ALIASES:
                return h
    # Primary score: e.g. "Decimal score" in SIUSData export
    if target_norm == _normalize(PRIMARY_SCORE):
        for h in csv_headers:
            hn = _normalize(h)
            if hn in PRIMARY_SCORE_ALIASES or ("decimal" in hn and "score" in hn):
                return h
    # Secondary score
    if target_norm == _normalize(SECONDARY_SCORE):
        for h in csv_headers:
            if _normalize(h) in SECONDARY_SCORE_ALIASES:
                return h
    return None


def suggest_columns(
    csv_headers: list[str],
    fields_path: Optional[Path] = None,
) -> dict[str, Optional[str]]:
    """
    Suggest CSV column for Start NR, Primary score, Secondary score.
    Returns { "start_nr": csv_header or None, "primary_score": ..., "secondary_score": ... }.
    """
    out = {
        "start_nr": match_csv_header_to_field(csv_headers, START_NR),
        "primary_score": match_csv_header_to_field(csv_headers, PRIMARY_SCORE),
        "secondary_score": match_csv_header_to_field(csv_headers, SECONDARY_SCORE),
    }
    # Fallback: if no Start NR match, use first column
    if not out["start_nr"] and csv_headers:
        out["start_nr"] = csv_headers[0]
    return out
