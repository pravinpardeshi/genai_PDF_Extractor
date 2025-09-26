from __future__ import annotations

from typing import List, Any, Dict
from pathlib import Path
import pdfplumber
import pandas as pd


Table = Dict[str, Any]


def _normalize_table(raw_rows: list[list[Any]]) -> dict:
    # Use first non-empty row as headers if possible
    headers: list[str] = []
    data_rows: list[list[Any]] = []

    for i, row in enumerate(raw_rows):
        if row and any(cell is not None and str(cell).strip() != "" for cell in row):
            headers = [str(c).strip() if c is not None else "" for c in row]
            data_rows = raw_rows[i + 1 :]
            break

    # Clean data rows
    cleaned_rows: list[list[Any]] = []
    for r in data_rows:
        cleaned_rows.append([(None if (c is None or str(c).strip() == "") else c) for c in r])

    return {"headers": headers, "rows": cleaned_rows}


def extract_tables(pdf_path: Path) -> List[Table]:
    tables: list[Table] = []
    with pdfplumber.open(pdf_path) as pdf:
        for p_idx, page in enumerate(pdf.pages, start=1):
            # try two strategies: lattice and stream
            table_settings = {
                "vertical_strategy": "lines",
                "horizontal_strategy": "lines",
                "explicit_vertical_lines": [],
                "explicit_horizontal_lines": [],
                "intersection_y_tolerance": 2,
                "intersection_x_tolerance": 2,
            }
            raw_tables = page.extract_tables(table_settings=table_settings) or []
            if not raw_tables:
                raw_tables = page.extract_tables() or []

            for t_idx, raw in enumerate(raw_tables):
                norm = _normalize_table(raw)
                tables.append(
                    {
                        "page": p_idx,
                        "table_index": t_idx,
                        "headers": norm["headers"],
                        "rows": norm["rows"],
                    }
                )
    return tables
