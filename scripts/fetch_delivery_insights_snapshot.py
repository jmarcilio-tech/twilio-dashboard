"""
Snapshot para alinhar com Twilio Console: SMS > Insights > Delivery & Errors
(Past N hours, Outgoing, contagens por mensagem + segmentos).

Usa Messages.json em modo activity (date_sent OU date_created na janela UTC),
igual ao script de paridade NS.

Env:
  DELIVERY_INSIGHTS_HOURS — default 4 (Past 4 hours na consola)
  DELIVERY_INSIGHTS_LIST_MODE — activity (default) | sent
  DELIVERY_INSIGHTS_MAX_PAGES — default 150
  DELIVERY_INSIGHTS_STOP_EMPTY — default 5
  DELIVERY_INSIGHTS_WRITE_CSV — 1 grava conf_delivery_insights_4h.csv na raiz
  DELIVERY_DIRECTION — outbound (default) | all
  TEST_INSIGHTS_ACCOUNT — filtrar por nome (ex. NS); vazio = todas

Saida: conf_delivery_insights_4h.csv
"""
from __future__ import annotations

import csv
import os
import sys
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(ROOT, ".env"))

CATEGORIAS = [
    "Delivered",
    "Failed",
    "Undelivered",
    "Sent",
    "Sending",
    "Delivery_Unknown",
    "Accepted",
    "Queued",
]

CSV_FIELDS = [
    "Conta",
    "Categoria",
    "Insights_Hours",
    "List_Mode",
    "Direcao",
    "Janela_Inicio_Utc",
    "Janela_Fim_Utc",
    "Insight_Delivered_Msgs",
    "Insight_Failed_Msgs",
    "Insight_Undelivered_Msgs",
    "Insight_Sent_Msgs",
    "Insight_Delivery_Unknown_Msgs",
    "Insight_Total_Msgs",
    "Mensagens",
    "Segmentos",
    "Delivered_Seg",
    "Failed_Seg",
    "Undelivered_Seg",
    "Sent_Seg",
    "Sending_Seg",
    "Delivery_Unknown_Seg",
    "Accepted_Seg",
    "Queued_Seg",
    "Api_Pages",
    "Api_Pages_Capped",
    "Github_Run_Id",
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


def empty_stats():
    d = {k: 0 for k in CATEGORIAS}
    d["Total"] = 0
    return d


def insight_five_from_msg_stats(stats_msg: dict) -> dict:
    unk = (
        stats_msg["Sending"]
        + stats_msg["Delivery_Unknown"]
        + stats_msg["Accepted"]
        + stats_msg["Queued"]
    )
    return {
        "Delivered": stats_msg["Delivered"],
        "Failed": stats_msg["Failed"],
        "Delivery_Unknown": unk,
        "Undelivered": stats_msg["Undelivered"],
        "Sent": stats_msg["Sent"],
    }


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


def collect_insights_for_account(
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
) -> dict:
    session = requests.Session()
    session.auth = HTTPBasicAuth(sid, token)
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    params: dict = {"PageSize": 1000}
    if list_mode == "sent":
        params["DateSent>"] = since_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    stats_msg = empty_stats()
    stats_seg = empty_stats()
    pagina = 0
    consecutive_empty = 0
    capped = False

    while url:
        if list_mode == "activity" and pagina >= max_pages:
            capped = True
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
            in_page += 1
            ch = classificar_status(m.get("status"))
            segs = int(m.get("num_segments", 1) or 1)
            stats_msg[ch] += 1
            stats_msg["Total"] += 1
            stats_seg[ch] += segs
            stats_seg["Total"] += segs

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

    ins = insight_five_from_msg_stats(stats_msg)
    return {
        "nome": nome,
        "cat": cat,
        "stats_msg": stats_msg,
        "stats_seg": stats_seg,
        "insight_five": ins,
        "api_pages": pagina,
        "api_pages_capped": capped,
    }


def main() -> int:
    hours = float(os.getenv("DELIVERY_INSIGHTS_HOURS", "4"))
    list_mode = (os.getenv("DELIVERY_INSIGHTS_LIST_MODE") or "activity").strip().lower()
    if list_mode not in ("sent", "activity"):
        list_mode = "activity"
    max_pages = int(os.getenv("DELIVERY_INSIGHTS_MAX_PAGES", "150"))
    stop_empty = int(os.getenv("DELIVERY_INSIGHTS_STOP_EMPTY", "5"))
    direction = (os.getenv("DELIVERY_DIRECTION") or "outbound").strip().lower()
    if direction not in ("outbound", "all"):
        direction = "outbound"
    write_csv = os.getenv("DELIVERY_INSIGHTS_WRITE_CSV", "").strip().lower() in ("1", "true", "yes")
    pick = (os.getenv("TEST_INSIGHTS_ACCOUNT") or "").strip().lower()
    agora = utc_now()
    since_dt = agora - timedelta(hours=hours)
    gh_run = os.getenv("GITHUB_RUN_ID", "").strip()
    extraido = agora.strftime("%Y-%m-%dT%H:%M:%SZ")

    print(
        f"# Delivery Insights snapshot\n"
        f"- agora_utc: {extraido}\n"
        f"- janela: ultimas {hours:g} h  [{since_dt.strftime('%Y-%m-%dT%H:%M:%SZ')} .. {extraido}]\n"
        f"- list_mode={list_mode} direction={direction} max_pages={max_pages}\n"
    )

    rows = []
    for acc in accounts_from_env():
        if not acc["sid"] or not acc["token"]:
            continue
        if pick and pick not in acc["nome"].lower():
            continue
        try:
            r = collect_insights_for_account(
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
        sm, sg = r["stats_msg"], r["stats_seg"]
        ins = r["insight_five"]
        rows.append(
            {
                "Conta": r["nome"],
                "Categoria": r["cat"],
                "Insights_Hours": hours,
                "List_Mode": list_mode,
                "Direcao": direction,
                "Janela_Inicio_Utc": since_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "Janela_Fim_Utc": extraido,
                "Insight_Delivered_Msgs": ins["Delivered"],
                "Insight_Failed_Msgs": ins["Failed"],
                "Insight_Undelivered_Msgs": ins["Undelivered"],
                "Insight_Sent_Msgs": ins["Sent"],
                "Insight_Delivery_Unknown_Msgs": ins["Delivery_Unknown"],
                "Insight_Total_Msgs": sm["Total"],
                "Mensagens": sm["Total"],
                "Segmentos": sg["Total"],
                "Delivered_Seg": sg["Delivered"],
                "Failed_Seg": sg["Failed"],
                "Undelivered_Seg": sg["Undelivered"],
                "Sent_Seg": sg["Sent"],
                "Sending_Seg": sg["Sending"],
                "Delivery_Unknown_Seg": sg["Delivery_Unknown"],
                "Accepted_Seg": sg["Accepted"],
                "Queued_Seg": sg["Queued"],
                "Api_Pages": r["api_pages"],
                "Api_Pages_Capped": 1 if r["api_pages_capped"] else 0,
                "Github_Run_Id": gh_run,
                "Extraido_Utc": extraido,
            }
        )
        print(
            f"## {acc['nome']}\n"
            f"- msgs total: {sm['Total']} | segmentos: {sg['Total']} | paginas: {r['api_pages']}"
            f"{' (cap)' if r['api_pages_capped'] else ''}\n"
            f"- Insight 5: delivered={ins['Delivered']} failed={ins['Failed']} "
            f"undelivered={ins['Undelivered']} sent={ins['Sent']} unknown={ins['Delivery_Unknown']}\n"
        )

    if write_csv and rows:
        path = os.path.join(ROOT, "conf_delivery_insights_4h.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            w.writeheader()
            w.writerows(rows)
        print(f"CSV: {path} ({len(rows)} linhas)")
    elif not rows:
        print("Nenhuma linha gerada (credenciais ou filtro TEST_INSIGHTS_ACCOUNT).")
    else:
        print("DELIVERY_INSIGHTS_WRITE_CSV nao ativo — CSV nao escrito.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
