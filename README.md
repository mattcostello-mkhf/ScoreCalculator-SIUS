# SIUS Score Calculator

A small Python app to load **SIUS AG** export CSV files (e.g. from SIUSData), pick the ID and score columns, and **summarize scores by ID** (sum, count, mean). Works on macOS and Windows.

## Two ways to run

- **Web UI (default)** — Opens in your browser. Use this on **Mac** if the app crashes when opening a window (Apple’s Tk can crash during init). Same UI on Windows.
- **Tkinter window** — Native desktop window. Use `python app_tk.py` on **Windows** if you prefer a single window; on Mac, prefer the web UI if you see a crash.

## SIUS format

- Exports are usually **semicolon-delimited** (`;`).
- Typical columns: Start number (ID), decimal score, sighting, target number, radius, time, inner ten, x/y, and others. The app auto-detects delimiter and suggests ID/score columns; you can change them in the UI.

## Requirements

- Python **3.8+**
- Install deps: `pip install -r requirements.txt` (Flask for the web UI)

## Run on Mac or Windows

```bash
cd ScoreCalculator
pip install -r requirements.txt
python3 -m app
```

Your browser will open at http://127.0.0.1:5000/. Upload a SIUS CSV, set the ID and score columns, and view the summary.

## Run (Tkinter window – e.g. on Windows)

```bash
python app_tk.py
```

## If Python crashed on Mac (Tk)

The crash happens inside **Tk** during startup (Tcl_Panic / TkpInit). Apple’s Command Line Tools Python uses an old Tcl/Tk 8.5 that can abort on newer macOS. **Fix:** use the web UI instead: run `python app.py` (or `python app_web.py`). No Tk is used; the app opens in your browser.

## Project layout

- `app.py` — Entry point; runs the web UI.
- `app_web.py` — Flask web app (upload CSV, column selection, summary).
- `app_tk.py` — Tkinter desktop GUI (optional).
- `sius_csv.py` — CSV loading, delimiter/column detection, summary-by-ID logic.
- `static/index.html` — Web UI page.

## Porting to Windows

Use the same repo on Windows:

```bash
pip install -r requirements.txt
python -m app
```

To build a standalone Windows executable (web UI in a single process):

```bash
pip install pyinstaller
pyinstaller --onefile --name "SIUS Score Calculator" app_web.py
```

Then run the generated `.exe`; it will start the server. Open http://127.0.0.1:5000/ in a browser, or use `--add-data` and a small launcher that opens the browser automatically (as in `app_web.main()`).
# ScoreCalculator-SIUS
