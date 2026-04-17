"""
Time series 15 min: contagens por MENSAGEM (legenda Insight 5) por slot UTC,
para alinhar filtros 5m/15m/1h/4h/hoje/ontem na UI sem usar o snapshot fixo de 4h.

Agrupa Messages API (activity) por Slot_15min igual a conf_delivery_horario.csv.

Env:
  DELIVERY_INSIGHTS_TS_HOURS — default 72 (profundidade a paginar para tras em UTC)
  DELIVERY_INSIGHTS_TS_LIST_MODE — activity (default) | sent
  DELIVERY_INSIGHTS_TS_MAX_PAGES — default 1000 (paginas Messages API em activity; ~1M msgs/conta/run — subir se ainda subcontar vs Insights)
  DELIVERY_INSIGHTS_TS_STOP_EMPTY — default 8
  DELIVERY_INSIGHTS_TS_WRITE_CSV — 1 grava conf_delivery_insights_timeseries.csv
  DELIVERY_DIRECTION — outbound (default) | all
  TEST_INSIGHTS_TS_ACCOUNT — filtrar por nome; vazio = todas

Saida: conf_delivery_insights_timeseries.csv
Colunas:
  Conta,Categoria,Direcao,Slot_15min,Insight_Delivered_Msgs,Insight_Failed_Msgs,
  Insight_Undelivered_Msgs,Insight_Sent_Msgs,Insight_Delivery_Unknown_Msgs,Insight_Total_Msgs,Extraido_Utc
"""
from __future__ import annotations

import csv
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(ROOT, ".env"))

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


def utc_now():
    return datetime.now(timezone.utc)


def parse_twilio_dt(s: str):
    if not s or not str(s).strip():
        return None
    try:
        return parsedate_to_datetime(s.strip())
    except Exception:
        return None


def classificar_status(status_raw: str) -> str:
    s = (status_raw or "unknown").strip().lower()
    if s == "delivered":
        return "Delivered"
    if s == "failed":
        return "Failed"
    if s in ("undelivered", "rejected"):
        return "Undelivered"
    if s == "sent":
        return "Sent"
    if s == "sending":
        return "Sending"
    if s == "queued":
        return "Queued"
    if s == "accepted":
        return "Accepted"
    if s in (
        "",
        "unknown",
        "receiving",
        "received",
        "partially_delivered",
        "canceled",
        "cancelled",
        "scheduled",
    ):
        return "Delivery_Unknown"
    return "Delivery_Unknown"


def direction_ok(m: dict, direction: str) -> bool:
    if direction == "all":
        return True
    d = (m.get("direction") or "").strip().lower()
    return d.startswith("outbound")


def in_activity_time_window(m: dict, since_dt: datetime, until_dt: datetime) -> bool:
    dc = parse_twilio_dt(m.get("date_created") or "")
    ds = parse_twilio_dt(m.get("date_sent") or "")
    in_c = dc is not None and since_dt <= dc <= until_dt
    in_s = ds is not None and since_dt <= ds <= until_dt
    return in_c or in_s


def in_sent_window(m: dict, since_dt: datetime) -> bool:
    ds = parse_twilio_dt(m.get("date_sent") or "")
    return ds is not None and ds >= since_dt


def slot_15min_from_dt(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    ms = (dt.minute // 15) * 15
    return dt.strftime(f"%Y-%m-%d %H:{ms:02d}")


def message_timestamp_for_slot(m: dict) -> datetime | None:
    """Mesma prioridade que delivery_extractor._agrega_mensagem (date_sent, senao date_created)."""
    ds = parse_twilio_dt(m.get("date_sent") or "")
    if ds:
        return ds
    return parse_twilio_dt(m.get("date_created") or "")


def insight_increment_for_category(cat: str) -> tuple[str, int]:
    """Retorna (campo_insight, delta) com legenda de 5 estados."""
    if cat == "Delivered":
        return ("Insight_Delivered_Msgs", 1)
    if cat == "Failed":
        return ("Insight_Failed_Msgs", 1)
    if cat == "Undelivered":
        return ("Insight_Undelivered_Msgs", 1)
    if cat == "Sent":
        return ("Insight_Sent_Msgs", 1)
    return ("Insight_Delivery_Unknown_Msgs", 1)


def accounts_from_env():
    return [
        {"sid": os.getenv("RECUPERACAO_NS_SID"), "token": os.getenv("RECUPERACAO_NS_TOKEN"), "nome": "NS", "categoria": "Recuperação"},
        {"sid": os.getenv("BROADCAST_JOAO_SID"), "token": os.getenv("BROADCAST_JOAO_TOKEN"), "nome": "Joao", "categoria": "Broadcast"},
        {"sid": os.getenv("BROADCAST_BERNARDO_SID"), "token": os.getenv("BROADCAST_BERNARDO_TOKEN"), "nome": "Bernardo", "categoria": "Broadcast"},
        {"sid": os.getenv("BROADCAST_RAFA_SID"), "token": os.getenv("BROADCAST_RAFA_TOKEN"), "nome": "Rafa", "categoria": "Broadcast"},
        {"sid": os.getenv("STANDBY_HAVEN_SID"), "token": os.getenv("STANDBY_HAVEN_TOKEN"), "nome": "Havenmove", "categoria": "Standby"},
        {"sid": os.getenv("STANDBY_REHABLEAF_SID"), "token": os.getenv("STANDBY_REHABLEAF_TOKEN"), "nome": "Rehableaf", "categoria": "Standby"},
        {"sid": os.getenv("STANDBY_RICHARD_SID"), "token": os.getenv("STANDBY_RICHARD_TOKEN"), "nome": "Richard", "categoria": "Standby"},
        {"sid": os.getenv("STANDBY_NATUREMOVE_SID"), "token": os.getenv("STANDBY_NATUREMOVE_TOKEN"), "nome": "Naturemove", "categoria": "Standby"},
    ]


def collect_timeseries_for_account(
    sid: str,
    token: str,
    nome: str,
    cat: str,
    agora: datetime,
    since_dt: datetime,
    list_mode: str,
    max_pages: int,
    stop_empty: int,
    direction: str,
) -> dict[tuple[str, str], dict[str, int]]:
    """Retorna mapa (Slot_15min, Conta) -> contadores insight."""
    session = requests.Session()
    session.auth = HTTPBasicAuth(sid, token)
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    params: dict = {"PageSize": 1000}
    if list_mode == "sent":
        params["DateSent>"] = since_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    agg: dict[tuple[str, str], dict[str, int]] = defaultdict(
        lambda: {
            "Insight_Delivered_Msgs": 0,
            "Insight_Failed_Msgs": 0,
            "Insight_Undelivered_Msgs": 0,
            "Insight_Sent_Msgs": 0,
            "Insight_Delivery_Unknown_Msgs": 0,
        }
    )
    pagina = 0
    consecutive_empty = 0

    while url:
        if list_mode == "activity" and pagina >= max_pages:
            print(
                f"WARN {nome}: parou em DELIVERY_INSIGHTS_TS_MAX_PAGES={max_pages} "
                f"(~{max_pages * 1000} msgs lidas); totais por slot podem ficar **abaixo** do "
                f"Messaging Insights (consola agrega tudo; REST lista com teto de paginas)."
            )
            break
        r = session.get(url, params=params, timeout=90)
        if r.status_code != 200:
            raise RuntimeError(f"{nome}: HTTP {r.status_code} {r.text[:300]}")
        body = r.json()
        pagina += 1
        in_page = 0
        for m in body.get("messages", []):
            if not direction_ok(m, direction):
                continue
            if list_mode == "activity":
                if not in_activity_time_window(m, since_dt, agora):
                    continue
            else:
                if not in_sent_window(m, since_dt):
                    continue
            ts = message_timestamp_for_slot(m)
            if ts is None:
                continue
            slot = slot_15min_from_dt(ts)
            ch = classificar_status(m.get("status"))
            field, _ = insight_increment_for_category(ch)
            key = (slot, nome)
            agg[key][field] += 1
            in_page += 1

        if list_mode == "activity":
            if in_page == 0:
                consecutive_empty += 1
                if consecutive_empty >= stop_empty:
                    break
            else:
                consecutive_empty = 0

        nxt = body.get("next_page_uri")
        url = f"https://api.twilio.com{nxt}" if nxt else None
        params = {}

    return agg


def main() -> int:
    hours = float(os.getenv("DELIVERY_INSIGHTS_TS_HOURS", "72"))
    list_mode = (os.getenv("DELIVERY_INSIGHTS_TS_LIST_MODE") or "activity").strip().lower()
    if list_mode not in ("sent", "activity"):
        list_mode = "activity"
    max_pages = int(os.getenv("DELIVERY_INSIGHTS_TS_MAX_PAGES", "1000"))
    stop_empty = int(os.getenv("DELIVERY_INSIGHTS_TS_STOP_EMPTY", "8"))
    direction = (os.getenv("DELIVERY_DIRECTION") or "outbound").strip().lower()
    if direction not in ("outbound", "all"):
        direction = "outbound"
    write_csv = os.getenv("DELIVERY_INSIGHTS_TS_WRITE_CSV", "").strip().lower() in ("1", "true", "yes")
    pick = (os.getenv("TEST_INSIGHTS_TS_ACCOUNT") or "").strip().lower()

    agora = utc_now()
    since_dt = agora - timedelta(hours=hours)
    extraido = agora.strftime("%Y-%m-%dT%H:%M:%SZ")

    print(
        f"# Delivery Insights timeseries (15 min slots)\n"
        f"- agora_utc: {extraido}\n"
        f"- profundidade: {hours:g} h\n"
        f"- list_mode={list_mode} direction={direction}\n"
    )

    merged: dict[tuple[str, str, str], dict[str, int]] = {}
    for acc in accounts_from_env():
        if not acc["sid"] or not acc["token"]:
            continue
        if pick and pick not in acc["nome"].lower():
            continue
        try:
            part = collect_timeseries_for_account(
                acc["sid"],
                acc["token"],
                acc["nome"],
                acc["categoria"],
                agora,
                since_dt,
                list_mode,
                max_pages,
                stop_empty,
                direction,
            )
        except Exception as e:
            print(f"**{acc['nome']}** ERRO: {e}\n")
            continue
        for (slot, nome), d in part.items():
            key3 = (slot, nome, acc["categoria"])
            if key3 not in merged:
                merged[key3] = {
                    "Insight_Delivered_Msgs": 0,
                    "Insight_Failed_Msgs": 0,
                    "Insight_Undelivered_Msgs": 0,
                    "Insight_Sent_Msgs": 0,
                    "Insight_Delivery_Unknown_Msgs": 0,
                }
            for k in merged[key3]:
                merged[key3][k] += d.get(k, 0)
        print(f"## {acc['nome']}: {len(part)} chaves slot")

    rows = []
    for (slot, nome, cat), d in sorted(merged.items(), key=lambda x: (x[0][0], x[0][1], x[0][2])):
        tot = sum(
            d[k]
            for k in (
                "Insight_Delivered_Msgs",
                "Insight_Failed_Msgs",
                "Insight_Undelivered_Msgs",
                "Insight_Sent_Msgs",
                "Insight_Delivery_Unknown_Msgs",
            )
        )
        rows.append(
            {
                "Conta": nome,
                "Categoria": cat,
                "Direcao": direction,
                "Slot_15min": slot,
                "Insight_Delivered_Msgs": d["Insight_Delivered_Msgs"],
                "Insight_Failed_Msgs": d["Insight_Failed_Msgs"],
                "Insight_Undelivered_Msgs": d["Insight_Undelivered_Msgs"],
                "Insight_Sent_Msgs": d["Insight_Sent_Msgs"],
                "Insight_Delivery_Unknown_Msgs": d["Insight_Delivery_Unknown_Msgs"],
                "Insight_Total_Msgs": tot,
                "Extraido_Utc": extraido,
            }
        )

    if write_csv and rows:
        path = os.path.join(ROOT, "conf_delivery_insights_timeseries.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            w.writeheader()
            w.writerows(rows)
        print(f"CSV: {path} ({len(rows)} linhas)")
    elif not rows:
        print("Nenhuma linha.")
    else:
        print("DELIVERY_INSIGHTS_TS_WRITE_CSV inativo.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
