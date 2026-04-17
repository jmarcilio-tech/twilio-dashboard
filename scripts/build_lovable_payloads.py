#!/usr/bin/env python3
"""
Gera JSON por aba em data/lovable/ para consumo pela Lovable (fetch único por ecrã, sem ambiguidade).

Entrada: CSVs já gerados no repo (não chama APIs).
Saída: billing.json, delivery.json, finance.json, saldo.json

Uso: na raiz do repo: python scripts/build_lovable_payloads.py
"""
from __future__ import annotations

import csv
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT_DIR = os.path.join(ROOT, "data", "lovable")
ORG_SUM = "__ORG_SUM__"

# Evita JSON gigante no raw GitHub para séries enormes (o CSV completo continua na raiz do repo).
MAX_HORARIO_ROWS = 8000
MAX_TIMESERIES_ROWS = 5000
MAX_BY_CATEGORY_ROWS = 15000


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_csv(path: str) -> list[dict[str, str]]:
    if not os.path.isfile(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_json_file(path: str) -> Any | None:
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def split_usage_snapshot(rows: list[dict[str, str]]) -> tuple[dict[str, str] | None, list[dict[str, str]]]:
    org: dict[str, str] | None = None
    accounts: list[dict[str, str]] = []
    for r in rows:
        c = (r.get("Conta") or "").strip()
        if c == ORG_SUM:
            org = r
        elif c:
            accounts.append(r)
    return org, accounts


def build_billing() -> dict[str, Any]:
    rolling_rows = read_csv(os.path.join(ROOT, "conf_usage_billing_snapshot.csv"))
    month_rows = read_csv(os.path.join(ROOT, "month", "conf_usage_billing_snapshot.csv"))

    org_r, acc_r = split_usage_snapshot(rolling_rows)
    org_m, acc_m = split_usage_snapshot(month_rows)

    by_cat_r = read_csv(os.path.join(ROOT, "conf_usage_billing_by_category.csv"))
    by_cat_m = read_csv(os.path.join(ROOT, "month", "conf_usage_billing_by_category.csv"))

    daily_r = read_csv(os.path.join(ROOT, "conf_usage_billing_daily.csv"))
    daily_m = read_csv(os.path.join(ROOT, "month", "conf_usage_billing_daily.csv"))

    def clip(name: str, rows: list[dict[str, str]], max_rows: int) -> tuple[list[dict[str, str]], bool]:
        if len(rows) <= max_rows:
            return rows, False
        return rows[:max_rows], True

    bcr, trunc_cr = clip("by_category_rolling", by_cat_r, MAX_BY_CATEGORY_ROWS)
    bcm, trunc_cm = clip("by_category_month", by_cat_m, MAX_BY_CATEGORY_ROWS)

    return {
        "meta": {
            "schema_version": 1,
            "tab": "billing",
            "generated_utc": utc_now_iso(),
            "org_sum_row_conta": ORG_SUM,
            "hints": {
                "rolling.org.TotalPrice_Totalprice": "KPI gasto org modo ~24h (coluna igual ao CSV snapshot).",
                "month.org.TotalPrice_Totalprice": "KPI gasto org modo Mês UTC (quando month não é null).",
                "rolling.accounts[] / month.accounts[]": "Por conta; campo TotalPrice_Totalprice por linha.",
                "rolling.by_category": "Detalhe Usage/Records por categoria (pode estar truncado — ver meta.truncated).",
            },
            "truncated": {
                "by_category_rolling": trunc_cr,
                "by_category_month": trunc_cm,
            },
            "row_counts": {
                "by_category_rolling": len(by_cat_r),
                "by_category_month": len(by_cat_m),
                "daily_rolling": len(daily_r),
                "daily_month": len(daily_m),
            },
            "csv_sources": {
                "snapshot_rolling": "conf_usage_billing_snapshot.csv",
                "snapshot_month": "month/conf_usage_billing_snapshot.csv",
                "by_category_rolling": "conf_usage_billing_by_category.csv",
                "by_category_month": "month/conf_usage_billing_by_category.csv",
                "daily_rolling": "conf_usage_billing_daily.csv",
                "daily_month": "month/conf_usage_billing_daily.csv",
            },
        },
        "rolling": {
            "range": org_r.get("Range") if org_r else None,
            "extraido_utc": org_r.get("Extraido_Utc") if org_r else None,
            "org": org_r,
            "accounts": acc_r,
            "by_category": bcr,
            "daily": daily_r,
        },
        "month": (
            {
                "range": org_m.get("Range") if org_m else None,
                "extraido_utc": org_m.get("Extraido_Utc") if org_m else None,
                "org": org_m,
                "accounts": acc_m,
                "by_category": bcm,
                "daily": daily_m,
            }
            if month_rows
            else None
        ),
    }


def build_delivery() -> dict[str, Any]:
    state = read_json_file(os.path.join(ROOT, "delivery_sync_state.json"))
    stats = read_csv(os.path.join(ROOT, "conf_delivery_stats.csv"))
    insights = read_csv(os.path.join(ROOT, "conf_delivery_insights_4h.csv"))

    horario_all = read_csv(os.path.join(ROOT, "conf_delivery_horario.csv"))
    horario_clip, hor_trunc = (
        (horario_all[:MAX_HORARIO_ROWS], True) if len(horario_all) > MAX_HORARIO_ROWS else (horario_all, False)
    )

    ts_all = read_csv(os.path.join(ROOT, "conf_delivery_insights_timeseries.csv"))
    ts_clip, ts_trunc = (
        (ts_all[:MAX_TIMESERIES_ROWS], True) if len(ts_all) > MAX_TIMESERIES_ROWS else (ts_all, False)
    )

    hist = read_csv(os.path.join(ROOT, "conf_delivery_stats_history.csv"))

    return {
        "meta": {
            "schema_version": 1,
            "tab": "delivery",
            "generated_utc": utc_now_iso(),
            "hints": {
                "stats_quick": "conf_delivery_stats.csv — snapshot ~5 min por conta.",
                "insights_4h": "Past N h estilo consola — conf_delivery_insights_4h.csv.",
                "horario": "Slots 15 min UTC; pode estar truncado em meta.truncated.horario.",
                "insights_timeseries": "Evolução por slot; pode estar truncado em meta.truncated.timeseries.",
            },
            "truncated": {"horario": hor_trunc, "timeseries": ts_trunc},
            "row_counts": {
                "horario": len(horario_all),
                "timeseries": len(ts_all),
                "history": len(hist),
            },
            "csv_sources": {
                "stats": "conf_delivery_stats.csv",
                "insights_4h": "conf_delivery_insights_4h.csv",
                "horario": "conf_delivery_horario.csv",
                "timeseries": "conf_delivery_insights_timeseries.csv",
                "history": "conf_delivery_stats_history.csv",
                "state": "delivery_sync_state.json",
            },
        },
        "pipeline_state": state,
        "stats_quick": stats,
        "insights_4h": insights,
        "horario": horario_clip,
        "insights_timeseries": ts_clip,
        "history": hist,
    }


def build_finance() -> dict[str, Any]:
    total = read_csv(os.path.join(ROOT, "conf_total_marco.csv"))
    det = read_csv(os.path.join(ROOT, "conf_detalhado_marco.csv"))
    return {
        "meta": {
            "schema_version": 1,
            "tab": "finance",
            "generated_utc": utc_now_iso(),
            "hints": {
                "total_marco": "Visão geral por Data/Conta — gráficos executivos.",
                "detalhado_marco": "Auditoria por Grupo_Gasto / categoria.",
            },
            "csv_sources": {
                "total": "conf_total_marco.csv",
                "detalhado": "conf_detalhado_marco.csv",
            },
        },
        "total_marco": total,
        "detalhado_marco": det,
    }


def build_saldo() -> dict[str, Any]:
    rows = read_csv(os.path.join(ROOT, "conf_saldos.csv"))
    return {
        "meta": {
            "schema_version": 1,
            "tab": "saldo",
            "generated_utc": utc_now_iso(),
            "hints": {
                "accounts": "Uma linha por Conta — Saldo_USD atual.",
            },
            "csv_sources": {"saldo": "conf_saldos.csv"},
        },
        "accounts": rows,
    }


def write_json(name: str, payload: dict[str, Any]) -> str:
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, name)
    with open(path, "w", encoding="utf-8") as f:
        # Compacto — menos MB no raw GitHub / menos tokens na Lovable.
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    return path


def main() -> int:
    write_json("billing.json", build_billing())
    write_json("delivery.json", build_delivery())
    write_json("finance.json", build_finance())
    write_json("saldo.json", build_saldo())
    print(f"OK — Lovable payloads em {OUT_DIR}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
