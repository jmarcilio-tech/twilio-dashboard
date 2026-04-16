"""
Paridade com Twilio Console: Monitor > Insights > SMS > Delivery & Errors
(filtro Outgoing, janela tipo PAST_H_4 = ultimas N horas UTC).

Usa a mesma logica de classificacao que delivery_extractor.py (REST Messages.json).
Documentacao consola (exemplo de URL com PAST_H_4 + OUTBOUND):
  https://console.twilio.com/us1/monitor/insights/sms?...

Env (.env na raiz do repo):
  RECUPERACAO_NS_SID, RECUPERACAO_NS_TOKEN

Env opcional:
  DELIVERY_INSIGHTS_HOURS — default 4 (Past 4 hours)
  NS_INSIGHTS_LIST_MODE — activity | sent (default activity; ignora DELIVERY_LIST_MODE do .env para nao confundir com o job de 5 min)
  DELIVERY_ACTIVITY_MAX_PAGES — default 120
  DELIVERY_ACTIVITY_STOP_EMPTY — default 5
"""
from __future__ import annotations

import os
import sys
from collections import Counter
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


def outbound_msg(m: dict) -> bool:
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


def main() -> int:
    sid = (os.getenv("RECUPERACAO_NS_SID") or "").strip()
    token = (os.getenv("RECUPERACAO_NS_TOKEN") or "").strip()
    if not sid or not token:
        print("Defina RECUPERACAO_NS_SID e RECUPERACAO_NS_TOKEN no .env.", file=sys.stderr)
        return 1

    hours = float(os.getenv("DELIVERY_INSIGHTS_HOURS", "4"))
    list_mode = (os.getenv("NS_INSIGHTS_LIST_MODE") or "activity").strip().lower()
    if list_mode not in ("sent", "activity"):
        list_mode = "activity"
    max_pages = int(os.getenv("DELIVERY_ACTIVITY_MAX_PAGES", "120"))
    stop_empty = int(os.getenv("DELIVERY_ACTIVITY_STOP_EMPTY", "5"))

    agora = utc_now()
    since_dt = agora - timedelta(hours=hours)

    session = requests.Session()
    session.auth = HTTPBasicAuth(sid, token)
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    params: dict = {"PageSize": 1000}
    if list_mode == "sent":
        params["DateSent>"] = since_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    stats_msg = empty_stats()
    raw_status = Counter()
    pagina = 0
    consecutive_empty = 0
    capped = False

    while url:
        if list_mode == "activity" and pagina >= max_pages:
            capped = True
            break
        r = session.get(url, params=params, timeout=90)
        if r.status_code != 200:
            print(f"HTTP {r.status_code} {r.text[:400]}", file=sys.stderr)
            return 1
        body = r.json()
        pagina += 1
        in_page = 0
        for m in body.get("messages", []):
            if not outbound_msg(m):
                continue
            if list_mode == "activity":
                if not in_activity_time_window(m, since_dt, agora):
                    continue
            else:
                if not in_sent_window(m, since_dt):
                    continue
            in_page += 1
            st = (m.get("status") or "").strip().lower()
            raw_status[st or "(vazio)"] += 1
            ch = classificar_status(m.get("status"))
            stats_msg[ch] += 1
            stats_msg["Total"] += 1

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
    ins_total = sum(ins.values())

    print("=" * 72)
    print("NS — API Messages (paridade Delivery & Errors / Outgoing)")
    print("=" * 72)
    print(f"Janela UTC:     ultimas {hours:g} h  [{since_dt.strftime('%Y-%m-%dT%H:%M:%SZ')} .. {agora.strftime('%Y-%m-%dT%H:%M:%SZ')}]")
    print(f"List mode:      {list_mode}  (consola Insights costuma aproximar-se mais a activity)")
    print(f"API pages:      {pagina}" + ("  (CAP max_pages)" if capped else ""))
    print()
    print("--- Legenda 5 estados (como painel Delivery & Errors, contagens por MENSAGEM) ---")
    print(f"  Delivered:         {ins['Delivered']}")
    print(f"  Failed:            {ins['Failed']}")
    print(f"  Undelivered:       {ins['Undelivered']}")
    print(f"  Sent:              {ins['Sent']}")
    print(f"  Delivery Unknown:  {ins['Delivery_Unknown']}  (Sending+Accepted+Queued+Delivery_Unknown internos)")
    print(f"  --- Total (soma 5): {ins_total}")
    print()
    print("--- Detalhe interno (8 buckets classificar_status) ---")
    for k in CATEGORIAS:
        print(f"  {k:<18} {stats_msg[k]}")
    print(f"  {'Total msgs':<18} {stats_msg['Total']}")
    print()
    print("--- Top status brutos devolvidos pela API (debug) ---")
    for st, n in raw_status.most_common(18):
        print(f"  {st[:40]:<40} {n}")
    print()
    print("Compare com o print Twilio (Total Outgoing Messages / Delivery Status).")
    print("Se divergir: NS_INSIGHTS_LIST_MODE=activity (default); suba DELIVERY_ACTIVITY_MAX_PAGES se cap.")
    print("Referencia Twilio Insights: https://www.twilio.com/docs/sms")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
