"""
SIUS Score Calculator - Web UI (no Tk).
Run on Mac when Tk crashes; same app works on Windows.
"""

from __future__ import annotations

import os
import time
import webbrowser
from pathlib import Path
from threading import Timer

from flask import Flask, request, jsonify, send_from_directory

from sius_csv import (
    load_data_rows_from_string,
    headers_from_field_names,
    summarize_decimal_integer,
    get_shots_for_start_nr,
)
from sius_fields import load_field_names, suggest_columns


def _column_index(headers: list[str], name: str):
    try:
        return headers.index(name)
    except ValueError:
        return None


def _unique_values(rows: list[list[str]], col_idx: int) -> list[str]:
    vals = set()
    for row in rows:
        if col_idx < len(row) and row[col_idx].strip():
            vals.add(row[col_idx].strip())
    return sorted(vals, key=lambda x: (not str(x).isdigit(), str(x).zfill(10) if str(x).isdigit() else x))

app = Flask(__name__, static_folder="static", static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB

# Per-tab in-memory store: { tab_id: { headers, rows, last_used } }
_tab_store: dict = {}
_TAB_TTL_SECONDS = 24 * 60 * 60  # 24 hours

# SIUSFields.txt path (same directory as this module)
_APP_DIR = Path(__file__).resolve().parent
SIUS_FIELDS_PATH = _APP_DIR / "SIUSFields.txt"


def _get_tab_id() -> str:
    return request.headers.get("X-Tab-ID") or "default"


def _get_tab_store() -> tuple[list[str], list[list[str]]]:
    """Return (headers, rows) for the current tab. Cleanup stale tabs."""
    tab_id = _get_tab_id()
    now = time.time()
    expired = [tid for tid, s in _tab_store.items() if now - s.get("last_used", 0) > _TAB_TTL_SECONDS]
    for tid in expired:
        del _tab_store[tid]
    if tab_id not in _tab_store:
        _tab_store[tab_id] = {"headers": [], "rows": [], "last_used": now}
    _tab_store[tab_id]["last_used"] = now
    store = _tab_store[tab_id]
    return store["headers"], store["rows"]


def _set_tab_store(headers: list[str], rows: list[list[str]]) -> None:
    tab_id = _get_tab_id()
    _tab_store[tab_id] = {"headers": headers, "rows": rows, "last_used": time.time()}


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "No file selected"}), 400
    try:
        content = f.stream.read().decode("utf-8", errors="replace")
    except Exception as e:
        return jsonify({"error": f"Could not read file: {e}"}), 400
    try:
        rows, delim = load_data_rows_from_string(content)
    except Exception as e:
        return jsonify({"error": f"Could not parse CSV: {e}"}), 400
    if not rows:
        return jsonify({"error": "File has no data rows"}), 400
    num_columns = max(len(r) for r in rows)
    if num_columns == 0:
        return jsonify({"error": "File has no columns"}), 400
    field_names = load_field_names(SIUS_FIELDS_PATH)
    if not field_names:
        return jsonify({"error": "SIUSFields.txt not found or empty; cannot assign column names"}), 400
    headers = headers_from_field_names(num_columns, field_names)
    _set_tab_store(headers, rows)
    suggested = suggest_columns(headers)
    relay_idx = _column_index(headers, "Relay")
    start_nr_idx = _column_index(headers, "Start NR")
    relays = _unique_values(rows, relay_idx) if relay_idx is not None else []
    start_nrs = _unique_values(rows, start_nr_idx) if start_nr_idx is not None else []
    return jsonify({
        "headers": headers,
        "start_nr": suggested["start_nr"] or headers[0],
        "primary_score": suggested["primary_score"],
        "secondary_score": suggested["secondary_score"],
        "row_count": len(rows),
        "relays": relays,
        "start_nrs": start_nrs,
    })


@app.route("/api/shots", methods=["POST"])
def shots():
    """Return shots for a given Start NR (from current relay/start_nrs filtered set), sorted descending by Time."""
    _current_headers, _current_rows = _get_tab_store()
    if not _current_headers or not _current_rows:
        return jsonify({"error": "Upload a file first"}), 400
    data = request.get_json() or {}
    suggested = suggest_columns(_current_headers)
    start_nr_column = suggested["start_nr"] or _current_headers[0]
    primary_column = suggested["primary_score"]
    secondary_column = suggested["secondary_score"]
    if not primary_column:
        return jsonify({"error": "No Primary score column in SIUSFields"}), 400
    relay_filter = data.get("relay")
    start_nrs_filter = data.get("start_nrs")
    start_nr_val = data.get("start_nr")
    if not start_nr_val:
        return jsonify({"error": "start_nr required"}), 400
    relay_idx = _column_index(_current_headers, "Relay")
    start_nr_idx = _column_index(_current_headers, "Start NR")
    rows = _current_rows
    if relay_filter is not None and relay_filter != "" and relay_idx is not None:
        rows = [r for r in rows if relay_idx < len(r) and (r[relay_idx] or "").strip() == relay_filter]
    if start_nrs_filter is not None and start_nr_idx is not None:
        if len(start_nrs_filter) == 0:
            rows = []
        else:
            allowed = set(str(s) for s in start_nrs_filter)
            rows = [r for r in rows if start_nr_idx < len(r) and (r[start_nr_idx] or "").strip() in allowed]
    time_column = "Time"
    if time_column not in _current_headers:
        time_column = next((h for h in _current_headers if "time" in h.lower()), "Time")
    try:
        shot_list = get_shots_for_start_nr(
            _current_headers,
            rows,
            start_nr_column,
            primary_column,
            secondary_column,
            time_column,
            start_nr_val,
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"shots": shot_list})


@app.route("/api/summary", methods=["POST"])
def summary():
    _current_headers, _current_rows = _get_tab_store()
    if not _current_headers or not _current_rows:
        return jsonify({"error": "Upload a file first"}), 400
    data = request.get_json() or {}
    suggested = suggest_columns(_current_headers)
    start_nr_column = suggested["start_nr"] or _current_headers[0]
    primary_column = suggested["primary_score"]
    secondary_column = suggested["secondary_score"]
    if not primary_column:
        return jsonify({"error": "No Primary score column in SIUSFields"}), 400
    relay_filter = data.get("relay")
    start_nrs_filter = data.get("start_nrs")
    excluded_indices = set(data.get("excluded_indices") or [])
    relay_idx = _column_index(_current_headers, "Relay")
    start_nr_idx = _column_index(_current_headers, "Start NR")
    rows = _current_rows
    if relay_filter is not None and relay_filter != "" and relay_idx is not None:
        rows = [r for r in rows if relay_idx < len(r) and (r[relay_idx] or "").strip() == relay_filter]
    if start_nrs_filter is not None and start_nr_idx is not None:
        if len(start_nrs_filter) == 0:
            rows = []
        else:
            allowed = set(str(s) for s in start_nrs_filter)
            rows = [r for r in rows if start_nr_idx < len(r) and (r[start_nr_idx] or "").strip() in allowed]
    if excluded_indices:
        rows = [r for i, r in enumerate(rows) if i not in excluded_indices]
    try:
        result = summarize_decimal_integer(
            _current_headers,
            rows,
            start_nr_column,
            primary_column,
            secondary_column,
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    for row in result:
        if "id" in row:
            row["Start NR"] = row.pop("id")
    columns = None
    if result:
        keys = list(result[0].keys())
        if "Start NR" in keys:
            keys.remove("Start NR")
            keys.insert(0, "Start NR")
        columns = keys
        result = [{k: row[k] for k in keys} for row in result]
    return jsonify({"summary": result, "columns": columns})


def _parse_float(val):
    try:
        return float((val or "").strip())
    except (ValueError, TypeError):
        return None


@app.route("/api/target-data", methods=["POST"])
def target_data():
    """Return included shots for a Start NR with X, Y, Decimal score for target view."""
    _current_headers, _current_rows = _get_tab_store()
    if not _current_headers or not _current_rows:
        return jsonify({"error": "Upload a file first"}), 400
    data = request.get_json() or {}
    suggested = suggest_columns(_current_headers)
    start_nr_column = suggested["start_nr"] or _current_headers[0]
    primary_column = suggested["primary_score"]
    secondary_column = suggested["secondary_score"]
    if not primary_column:
        return jsonify({"error": "No Primary score column in SIUSFields"}), 400
    relay_filter = data.get("relay")
    start_nrs_filter = data.get("start_nrs")
    excluded_indices = set(data.get("excluded_indices") or [])
    start_nr_val = data.get("start_nr")
    if not start_nr_val:
        return jsonify({"error": "start_nr required"}), 400
    relay_idx = _column_index(_current_headers, "Relay")
    start_nr_idx = _column_index(_current_headers, "Start NR")
    x_idx = _column_index(_current_headers, "X")
    y_idx = _column_index(_current_headers, "Y")
    if x_idx is None or y_idx is None:
        return jsonify({"error": "X and Y columns required for target view"}), 400
    rows = _current_rows
    if relay_filter is not None and relay_filter != "" and relay_idx is not None:
        rows = [r for r in rows if relay_idx < len(r) and (r[relay_idx] or "").strip() == relay_filter]
    if start_nrs_filter is not None and start_nr_idx is not None:
        if len(start_nrs_filter) == 0:
            rows = []
        else:
            allowed = set(str(s) for s in start_nrs_filter)
            rows = [r for r in rows if start_nr_idx < len(r) and (r[start_nr_idx] or "").strip() in allowed]
    if excluded_indices:
        rows = [r for i, r in enumerate(rows) if i not in excluded_indices]
    try:
        shot_list = get_shots_for_start_nr(
            _current_headers,
            rows,
            start_nr_column,
            primary_column,
            secondary_column,
            "Time",
            start_nr_val,
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    out = []
    for i, s in enumerate(shot_list):
        row_idx = s["index"]
        if row_idx < len(rows):
            row = rows[row_idx]
            x = _parse_float(row[x_idx]) if x_idx < len(row) else None
            y = _parse_float(row[y_idx]) if y_idx < len(row) else None
        else:
            x, y = None, None
        dec = s.get("Decimal score")
        out.append({"shot_num": i + 1, "x": x, "y": y, "decimal_score": dec})
    return jsonify({"start_nr": start_nr_val, "shots": out})


def open_browser():
    webbrowser.open("http://127.0.0.1:5000/")


def main():
    host = "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1"
    port = int(os.environ.get("PORT", 5000))
    if not os.environ.get("PORT"):
        Timer(1.0, open_browser).start()
    app.run(host=host, port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
