#!/usr/bin/env python3
"""Junta CSVs parciais do timeseries (uma conta por ficheiro) num único conf_delivery_insights_timeseries.csv."""
from __future__ import annotations

import csv
import glob
import os
import sys

# Copiado de fetch_delivery_insights_timeseries.py para evitar import circular
CSV_FIELDS = [
    "Conta",
    "Categoria",
    "Direcao",
    "Slot_15min",
    "Insight_Delivered_Msgs",
    "Insight_Failed_Msgs",
    "Insight_Undelivered_Msgs",
    "Insight_Sent_Msgs",
    "Insight_Delivery_Unknown_Msgs",
    "Insight_Total_Msgs",
    "Extraido_Utc",
]


def main() -> int:
    paths: list[str] = []
    for a in sys.argv[1:]:
        if os.path.isdir(a):
            paths.extend(sorted(glob.glob(os.path.join(a, "**", "*.csv"), recursive=True)))
        else:
            paths.extend(sorted(glob.glob(a)))
    paths = [p for p in paths if os.path.isfile(p)]
    if not paths:
        print("merge_delivery_insights_timeseries: nenhum ficheiro.", file=sys.stderr)
        return 1

    rows: list[dict] = []
    for p in paths:
        with open(p, newline="", encoding="utf-8") as f:
            r = csv.DictReader(f)
            for row in r:
                if not (row.get("Slot_15min") or "").strip():
                    continue
                rows.append(row)

    rows.sort(key=lambda x: (x.get("Slot_15min", ""), x.get("Conta", ""), x.get("Categoria", "")))

    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    out = os.path.join(root, "conf_delivery_insights_timeseries.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"merge: {len(paths)} parciais -> {out} ({len(rows)} linhas)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
