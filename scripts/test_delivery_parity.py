"""
Teste isolado: métricas de delivery (REST Messages) sem gravar CSV nem estado.

Uso (na raiz do repo ou a partir de scripts/):
  set PARITY_WINDOW_HOURS=4
  set TEST_DELIVERY_ACCOUNT=Joao
  python scripts/test_delivery_parity.py

Variáveis:
  PARITY_WINDOW_HOURS — janela rolante em horas (default 4).
  DELIVERY_DIRECTION — outbound | all (igual ao delivery_extractor).
  TEST_DELIVERY_ACCOUNT — nome da conta (ex.: Joao); vazio = só a primeira com credenciais.
  PARITY_ALL_ACCOUNTS=1 — percorrer todas as contas com credenciais (pode ser lento).
  PARITY_FILTER_BY_DATE_CREATED=1 — após DateSent>, só conta mensagens com date_created na janela (teste de alinhamento).
  PARITY_LIST_MODE=sent|activity — sent=DateSent> (igual ao pipeline; pode falhar mensagens sem date_sent).
    activity=lista sem filtro de data na API, inclui outbound se date_sent OU date_created cair na janela [agora-4h, agora];
    usa PARITY_ACTIVITY_MAX_PAGES (default 80, igual ao delivery_extractor) e PARITY_ACTIVITY_STOP_EMPTY (default 5).
  PARITY_DEBUG_STATUS=1 — imprime contagem por status bruto da API (mensagens ja filtradas como na agregacao).

Nota: Messaging Insights na consola não tem API REST pública com os mesmos rollups;
este script aproxima via Messages.json. O modo activity costuma aproximar mais do Total Messages
quando a consola mistura envios recentes com date_sent vazio.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

# Raiz do repositório (pai de scripts/)
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
load_dotenv(os.path.join(ROOT, ".env"))

from accounts_catalog import accounts_from_env

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


def empty_stats():
    d = {k: 0 for k in CATEGORIAS}
    d["Total"] = 0
    return d


def mensagem_conta_para_extracao(m: dict, direction_mode: str) -> bool:
    if direction_mode == "all":
        return True
    d = (m.get("direction") or "").strip().lower()
    return d.startswith("outbound")


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


def parse_twilio_dt(s: str) -> datetime | None:
    if not s or not str(s).strip():
        return None
    try:
        return parsedate_to_datetime(s.strip())
    except Exception:
        return None


def in_activity_time_window(m: dict, since_dt: datetime, until_dt: datetime) -> bool:
    """Inclui se date_created ou date_sent (quando existir) estiverem em [since_dt, until_dt] UTC."""
    dc = parse_twilio_dt(m.get("date_created") or "")
    ds = parse_twilio_dt(m.get("date_sent") or "")
    in_c = dc is not None and since_dt <= dc <= until_dt
    in_s = ds is not None and since_dt <= ds <= until_dt
    return in_c or in_s


def fetch_aggregates_sent(
    acc: dict,
    since_iso: str,
    direction_mode: str,
    client_filter_created: bool,
    since_dt: datetime,
    debug_raw: bool,
):
    """Agrega com DateSent> since_iso (igual delivery_extractor); opcional filtro date_created na janela."""
    sid, token = acc["sid"], acc["token"]
    session = requests.Session()
    session.auth = HTTPBasicAuth(sid, token)
    stats_msg = empty_stats()
    stats_seg = empty_stats()
    skipped_created = 0
    raw_counts: dict[str, int] = {}
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    params = {"DateSent>": since_iso, "PageSize": 1000}
    pages = 0

    while url:
        r = session.get(url, params=params, timeout=60)
        if r.status_code != 200:
            return None, r.status_code, f"http_{r.status_code}"
        body = r.json()
        pages += 1
        for m in body.get("messages", []):
            if not mensagem_conta_para_extracao(m, direction_mode):
                continue
            if client_filter_created:
                dc = parse_twilio_dt(m.get("date_created") or "")
                if dc is None or dc < since_dt:
                    skipped_created += 1
                    continue
            status = m.get("status", "unknown")
            chave = classificar_status(status)
            segs = int(m.get("num_segments", 1) or 1)
            stats_msg["Total"] += 1
            stats_seg["Total"] += segs
            stats_msg[chave] += 1
            stats_seg[chave] += segs
            if debug_raw:
                rk = (status or "").strip() or "(empty)"
                raw_counts[rk] = raw_counts.get(rk, 0) + 1
        next_uri = body.get("next_page_uri")
        url = f"https://api.twilio.com{next_uri}" if next_uri else None
        params = {}

    diag = f"excluidas_pos_datesent_created<{since_dt.isoformat()}: {skipped_created}" if client_filter_created else ""
    return (stats_msg, stats_seg, pages, raw_counts if debug_raw else None), 200, diag  # 4th: histograma ou None


def fetch_aggregates_activity(
    acc: dict,
    since_dt: datetime,
    until_dt: datetime,
    direction_mode: str,
    max_pages: int,
    stop_empty: int,
    debug_raw: bool,
):
    """Lista Messages sem DateSent na API; filtra outbound + janela em date_sent OU date_created."""
    sid, token = acc["sid"], acc["token"]
    session = requests.Session()
    session.auth = HTTPBasicAuth(sid, token)
    stats_msg = empty_stats()
    stats_seg = empty_stats()
    raw_counts: dict[str, int] = {}
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    params: dict = {"PageSize": 1000}
    pages = 0
    consecutive_empty = 0

    while url and pages < max_pages:
        r = session.get(url, params=params, timeout=60)
        if r.status_code != 200:
            return None, r.status_code, f"http_{r.status_code}"
        body = r.json()
        pages += 1
        in_page = 0
        for m in body.get("messages", []):
            if not mensagem_conta_para_extracao(m, direction_mode):
                continue
            if not in_activity_time_window(m, since_dt, until_dt):
                continue
            in_page += 1
            status = m.get("status", "unknown")
            chave = classificar_status(status)
            segs = int(m.get("num_segments", 1) or 1)
            stats_msg["Total"] += 1
            stats_seg["Total"] += segs
            stats_msg[chave] += 1
            stats_seg[chave] += segs
            if debug_raw:
                rk = (status or "").strip() or "(empty)"
                raw_counts[rk] = raw_counts.get(rk, 0) + 1
        if in_page == 0:
            consecutive_empty += 1
            if consecutive_empty >= stop_empty:
                break
        else:
            consecutive_empty = 0
        next_uri = body.get("next_page_uri")
        url = f"https://api.twilio.com{next_uri}" if next_uri else None
        params = {}

    diag = f"activity pages={pages} max={max_pages} stop_empty_streak={consecutive_empty}>={stop_empty}"
    return (stats_msg, stats_seg, pages, raw_counts if debug_raw else None), 200, diag  # 4th: histograma ou None


def rollup_insights_five(stats_msg: dict) -> dict:
    """Mesmos 5 rótulos do gráfico Delivery & Errors (Sending/Queued/Accepted/Unknown -> Delivery Unknown)."""
    unk = (
        stats_msg["Sending"]
        + stats_msg["Delivery_Unknown"]
        + stats_msg["Accepted"]
        + stats_msg["Queued"]
    )
    return {
        "Delivered": stats_msg["Delivered"],
        "Failed": stats_msg["Failed"],
        "Undelivered": stats_msg["Undelivered"],
        "Sent": stats_msg["Sent"],
        "Delivery Unknown": unk,
    }


def print_raw_status_histogram(raw_counts: dict[str, int]):
    if not raw_counts:
        return
    print("\n#### Status bruto API (contagem msgs agregadas)")
    print("| status | n |")
    print("|--------|--:|")
    for k, v in sorted(raw_counts.items(), key=lambda x: -x[1]):
        print(f"| {k} | {v} |")


def print_insights_five(stats_msg: dict):
    r = rollup_insights_five(stats_msg)
    tot = sum(r.values())
    print("\n#### Insights-style (5 buckets, msgs)")
    print("| status (consola) | msgs |")
    print("|------------------|-----:|")
    for k in ("Delivered", "Failed", "Delivery Unknown", "Undelivered", "Sent"):
        print(f"| {k} | {r[k]} |")
    print(f"| **Total (soma 5)** | **{tot}** |")
    print(f"| Total interno (8 buckets) | {stats_msg['Total']} |")


def print_block(title: str, stats_msg: dict, stats_seg: dict, extra: str = ""):
    print(f"\n### {title}")
    if extra:
        print(extra)
    print("| bucket | msgs | segs |")
    print("|--------|-----:|-----:|")
    for k in CATEGORIAS:
        print(f"| {k} | {stats_msg[k]} | {stats_seg[k]} |")
    taxa = round((stats_seg["Delivered"] / stats_seg["Total"] * 100), 2) if stats_seg["Total"] else 0.0
    print(f"| **Total** | **{stats_msg['Total']}** | **{stats_seg['Total']}** |")
    print(f"| % entregues (segs) | - | {taxa}% |")


def main():
    hours = float(os.getenv("PARITY_WINDOW_HOURS", "4"))
    direction = os.getenv("DELIVERY_DIRECTION", "outbound").strip().lower()
    if direction not in ("outbound", "all"):
        direction = "outbound"
    filter_created = os.getenv("PARITY_FILTER_BY_DATE_CREATED", "").strip().lower() in ("1", "true", "yes")
    list_mode = os.getenv("PARITY_LIST_MODE", "sent").strip().lower()
    if list_mode not in ("sent", "activity"):
        list_mode = "sent"
    max_act = int(os.getenv("PARITY_ACTIVITY_MAX_PAGES", "80"))
    stop_empty = int(os.getenv("PARITY_ACTIVITY_STOP_EMPTY", "5"))
    debug_raw = os.getenv("PARITY_DEBUG_STATUS", "").strip().lower() in ("1", "true", "yes")
    pick = (os.getenv("TEST_DELIVERY_ACCOUNT") or "").strip().lower()
    all_accounts = os.getenv("PARITY_ALL_ACCOUNTS", "").strip().lower() in ("1", "true", "yes")

    agora = utc_now()
    since_dt = agora - timedelta(hours=hours)
    since_iso = since_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    janela_desc = (
        f"ultimas {hours}h; API DateSent>={since_iso} (modo sent)"
        if list_mode == "sent"
        else f"ultimas {hours}h; modo activity (date_sent OU date_created em [{since_iso}, {agora.strftime('%Y-%m-%dT%H:%M:%SZ')}])"
    )
    print(
        f"# Parity test (isolado)\n"
        f"- agora_utc: {agora.strftime('%Y-%m-%dT%H:%M:%SZ')}\n"
        f"- janela: {janela_desc}\n"
        f"- PARITY_LIST_MODE: {list_mode}\n"
        f"- direcao: {direction}\n"
        f"- filtro extra date_created>=inicio_janela (so com sent+): {filter_created}\n"
        f"- conta(s): {pick or ('todas' if all_accounts else 'primeira com credenciais')}\n"
    )

    accounts = accounts_from_env()
    selected = []
    for a in accounts:
        if not a["sid"] or not a["token"]:
            continue
        if pick and pick not in a["nome"].lower():
            continue
        selected.append(a)
        if not pick and not all_accounts:
            break

    if not selected:
        print("Nenhuma conta selecionada (credenciais ou TEST_DELIVERY_ACCOUNT).")
        return 1
    if not pick and not all_accounts and len([x for x in accounts if x["sid"] and x["token"]]) > 1:
        print("(Aviso: so a primeira conta com credenciais. PARITY_ALL_ACCOUNTS=1 ou TEST_DELIVERY_ACCOUNT=nome para mais.)\n")

    for acc in selected:
        nome = acc["nome"]
        if list_mode == "activity":
            res, code, diag = fetch_aggregates_activity(
                acc, since_dt, agora, direction, max_act, stop_empty, debug_raw
            )
        else:
            res, code, diag = fetch_aggregates_sent(
                acc, since_iso, direction, filter_created, since_dt, debug_raw
            )
        if res is None:
            print(f"\n**{nome}**: HTTP {code} {diag}")
            continue
        stats_msg, stats_seg, pages, raw_hist = res
        extra = f"Paginas API: {pages}. {diag}".strip()
        print_block(f"{nome} [{acc['categoria']}]", stats_msg, stats_seg, extra)
        print_insights_five(stats_msg)
        if raw_hist:
            print_raw_status_histogram(raw_hist)

    print("\n---\nCompare Total msgs com Total Messages na consola (Outgoing); segs com o pipeline atual.")
    print("URL consola alinhada: tab deliveryAndErrors, PAST_H_4, OUTBOUND (UTC).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
