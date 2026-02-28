"""
SIUS Score Calculator - Tkinter desktop GUI.
Use on Windows when you want a native window; on Mac use app.py (web UI) if Tk crashes.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from typing import Optional

from sius_csv import (
    load_headers_and_rows,
    infer_column_types,
    summarize_by_id,
    DEFAULT_DELIMITER,
)


class SIUSScoreApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("SIUS Score Calculator")
        self.root.minsize(640, 480)
        self.root.geometry("900x600")

        self._file_path: Optional[Path] = None
        self._headers: list[str] = []
        self._rows: list[list[str]] = []
        self._summary: list[dict] = []

        self._build_ui()

    def _build_ui(self):
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill=tk.X)

        ttk.Button(top, text="Open SIUS CSV…", command=self._open_file).pack(side=tk.LEFT, padx=(0, 8))
        self._file_label = ttk.Label(top, text="No file loaded", foreground="gray")
        self._file_label.pack(side=tk.LEFT)

        # Column choices
        col_frame = ttk.LabelFrame(self.root, text="Columns", padding=8)
        col_frame.pack(fill=tk.X, padx=8, pady=4)

        id_row = ttk.Frame(col_frame)
        id_row.pack(fill=tk.X)
        ttk.Label(id_row, text="ID column:").pack(side=tk.LEFT, padx=(0, 8))
        self._id_var = tk.StringVar()
        self._id_combo = ttk.Combobox(id_row, textvariable=self._id_var, width=30, state="readonly")
        self._id_combo.pack(side=tk.LEFT)
        self._id_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_summary())

        score_row = ttk.Frame(col_frame)
        score_row.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(score_row, text="Score columns:").pack(side=tk.LEFT, padx=(0, 8))
        self._score_list_frame = ttk.Frame(score_row)
        self._score_list_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._score_vars: list[tk.BooleanVar] = []
        self._score_checks: list[ttk.Checkbutton] = []

        # Summary table
        summary_frame = ttk.LabelFrame(self.root, text="Summary by ID", padding=8)
        summary_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self._summary_tree = ttk.Treeview(summary_frame, show="headings", height=12, selectmode="browse")
        scroll_y = ttk.Scrollbar(summary_frame, orient=tk.VERTICAL, command=self._summary_tree.yview)
        scroll_x = ttk.Scrollbar(summary_frame, orient=tk.HORIZONTAL, command=self._summary_tree.xview)
        self._summary_tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)

        self._summary_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        scroll_x.pack(side=tk.BOTTOM, fill=tk.X)

        self._status = ttk.Label(self.root, text="Load a SIUS CSV file to begin.", foreground="gray")
        self._status.pack(fill=tk.X, padx=8, pady=4)

    def _open_file(self):
        path = filedialog.askopenfilename(
            title="Open SIUS CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        self._load_file(Path(path))

    def _load_file(self, path: Path):
        try:
            headers, rows = load_headers_and_rows(path)
        except Exception as e:
            messagebox.showerror("Error", f"Could not load file:\n{e}")
            return
        self._file_path = path
        self._headers = headers
        self._rows = rows
        self._file_label.config(text=path.name, foreground="")
        self._status.config(text=f"Loaded {len(rows)} rows, {len(headers)} columns.")

        id_cols, score_cols = infer_column_types(headers, rows)
        self._id_combo["values"] = headers
        if id_cols:
            self._id_var.set(id_cols[0])
        else:
            self._id_var.set(headers[0] if headers else "")

        # Score checkboxes
        for w in self._score_checks:
            w.destroy()
        self._score_vars.clear()
        self._score_checks.clear()
        for h in headers:
            if h == self._id_var.get():
                continue
            var = tk.BooleanVar(value=h in score_cols)
            self._score_vars.append(var)
            cb = ttk.Checkbutton(
                self._score_list_frame,
                text=h,
                variable=var,
                command=self._refresh_summary,
            )
            cb.pack(side=tk.LEFT, padx=(0, 12))
            self._score_checks.append(cb)

        self._refresh_summary()

    def _get_score_columns(self) -> list[str]:
        return [self._score_checks[i].cget("text") for i, v in enumerate(self._score_vars) if v.get()]

    def _refresh_summary(self):
        for c in self._summary_tree.get_children():
            self._summary_tree.delete(c)
        for col in self._summary_tree["columns"]:
            self._summary_tree.heading(col, text="")
            self._summary_tree.column(col, width=0)
        self._summary_tree["columns"] = []

        if not self._headers or not self._rows:
            return
        id_col = self._id_var.get()
        score_cols = self._get_score_columns()
        if not id_col:
            return
        summary = summarize_by_id(self._headers, self._rows, id_col, score_cols)
        self._summary = summary
        if not summary:
            return

        cols = ["id", "count"]
        for k in summary[0]:
            if k not in ("id", "count"):
                cols.append(k)
        self._summary_tree["columns"] = cols
        for c in cols:
            self._summary_tree.heading(c, text=c)
            self._summary_tree.column(c, width=80, minwidth=60)
        for row in summary:
            self._summary_tree.insert("", tk.END, values=[row.get(c, "") for c in cols])

    def run(self):
        self.root.mainloop()


def main():
    app = SIUSScoreApp()
    app.run()


if __name__ == "__main__":
    main()
