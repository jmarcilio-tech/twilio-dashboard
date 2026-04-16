"""
Snapshot de billing via API oficial Twilio Usage Records (proximo de Account Insights).

Documentacao: https://www.twilio.com/docs/usage/api/usage-record

Limitacao: StartDate/EndDate sao em GMT YYYY-MM-DD (granularidade diaria na maioria dos casos).
A consola "Last 24 hours" e uma janela rolante; este script cobre os dias civis UTC que
intersectam as ultimas N horas (pode diferir ligeiramente do card da consola).

Env:
  USAGE_SNAPSHOT_HOURS — default 24 (so usado em cover_days)
  USAGE_DATE_STRATEGY (default: rolling_24h_proxy) —
      rolling_24h_proxy — Usage/Records/Daily por categoria + mistura por hora na janela [agora-hours, agora] (~**Last 24h** Insights; pressupoe uso uniforme por hora em cada dia UTC).
      end_utc_day — um dia civil UTC (subestima Last 24h na maior parte do dia).
      twilio_offsets — StartDate=-1days EndDate=hoje (**soma dois dias GMT inteiros** — costuma **superar** Last 24h).
      cover_days — dias UTC tocados pela janela (1–2 dias completos na API).
      start_utc_day — so o dia UTC do inicio da janela.
      today_subresource — GET .../Usage/Records/Today.json.
  USAGE_UTC_DAY — se YYYY-MM-DD, forca StartDate=EndDate=esse dia (ignora USAGE_DATE_STRATEGY).
  TEST_USAGE_ACCOUNT — filtrar por nome (ex.: NS); vazio = todas com credenciais
  USAGE_WRITE_CSV — 1 grava conf_usage_billing_snapshot.csv na raiz do repo

Saida: totalprice (categoria totalprice), sms (count/usage/price). Para "SMS Transactions" na consola,
  testar **count** primeiro, depois **usage** (segmentos), conforme o card.
"""
from __future__ import annotations

import csv
import os
import sys
from datetime import datetime, timedelta, timezone

import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(ROOT, ".env"))


def utc_now():
    return datetime.now(timezone.utc)


def accounts_from_env():
    return [
        {"sid": os.getenv("RECUPERACAO_NS_SID"), "token": os.getenv("RECUPERACAO_NS_TOKEN"), "nome": "NS"},
        {"sid": os.getenv("BROADCAST_JOAO_SID"), "token": os.getenv("BROADCAST_JOAO_TOKEN"), "nome": "Joao"},
        {"sid": os.getenv("BROADCAST_BERNARDO_SID"), "token": os.getenv("BROADCAST_BERNARDO_TOKEN"), "nome": "Bernardo"},
        {"sid": os.getenv("BROADCAST_RAFA_SID"), "token": os.getenv("BROADCAST_RAFA_TOKEN"), "nome": "Rafa"},
        {"sid": os.getenv("STANDBY_HAVEN_SID"), "token": os.getenv("STANDBY_HAVEN_TOKEN"), "nome": "Havenmove"},
        {"sid": os.getenv("STANDBY_REHABLEAF_SID"), "token": os.getenv("STANDBY_REHABLEAF_TOKEN"), "nome": "Rehableaf"},
        {"sid": os.getenv("STANDBY_RICHARD_SID"), "token": os.getenv("STANDBY_RICHARD_TOKEN"), "nome": "Richard"},
        {"sid": os.getenv("STANDBY_NATUREMOVE_SID"), "token": os.getenv("STANDBY_NATUREMOVE_TOKEN"), "nome": "Naturemove"},
    ]


def parse_float(x) -> float:
    try:
        if x is None or x == "":
            return 0.0
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def parse_int(x) -> int:
    try:
        if x is None or x == "":
            return 0
        return int(float(x))
    except (TypeError, ValueError):
        return 0


def fetch_usage_records_url(sid: str, token: str, path: str, params: dict) -> list[dict]:
    session = requests.Session()
    session.auth = HTTPBasicAuth(sid, token)
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Usage/Records{path}.json"
    out: list[dict] = []
    page = 0
    while url:
        r = session.get(url, params=params, timeout=60)
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code} {r.text[:500]}")
        body = r.json()
        page += 1
        out.extend(body.get("usage_records", []))
        next_uri = body.get("next_page_uri")
        url = f"https://api.twilio.com{next_uri}" if next_uri else None
        params = {}
    return out


def fetch_usage_records(sid: str, token: str, params: dict) -> list[dict]:
    return fetch_usage_records_url(sid, token, "", params)


def utc_midnight(d: datetime) -> datetime:
    return datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=timezone.utc)


def overlap_hours_utc_day(t0: datetime, t1: datetime, day: datetime) -> float:
    ds = utc_midnight(day)
    de = ds + timedelta(days=1)
    a = max(t0, ds)
    b = min(t1, de)
    if b <= a:
        return 0.0
    return (b - a).total_seconds() / 3600.0


def fetch_daily_category(sid: str, token: str, category: str, start_d: str, end_d: str) -> list[dict]:
    params = {"Category": category, "StartDate": start_d, "EndDate": end_d, "PageSize": 1000}
    return fetch_usage_records_url(sid, token, "/Daily", params)


def blend_daily_metric(rows: list[dict], agora: datetime, hours: float, field: str) -> float:
    """Soma_v * (horas da janela [agora-hours, agora] sobre o dia v / 24)."""
    t1 = agora
    t0 = agora - timedelta(hours=hours)
    acc = 0.0
    for r in rows:
        sd = (r.get("start_date") or "")[:10]
        if len(sd) != 10:
            continue
        try:
            y, m_, d_ = int(sd[0:4]), int(sd[5:7]), int(sd[8:10])
            day = datetime(y, m_, d_, 0, 0, 0, tzinfo=timezone.utc)
        except ValueError:
            continue
        h = overlap_hours_utc_day(t0, t1, day)
        if h <= 0:
            continue
        v = parse_float(r.get(field))
        acc += v * (h / 24.0)
    return acc


def blended_headline_billing(sid: str, token: str, agora: datetime, hours: float) -> dict:
    """
    Proxy ~Last 24h (Account Insights): Daily por categoria + mistura por hora.
    sms_sub / sum_price exceto totalprice: snapshot do dia UTC corrente (auxiliar).
    """
    t0 = agora - timedelta(hours=hours)
    start_d = t0.strftime("%Y-%m-%d")
    end_d = agora.strftime("%Y-%m-%d")
    daily_tp = fetch_daily_category(sid, token, "totalprice", start_d, end_d)
    daily_sms = fetch_daily_category(sid, token, "sms", start_d, end_d)
    totalprice = blend_daily_metric(daily_tp, agora, hours, "price")
    sms_price = blend_daily_metric(daily_sms, agora, hours, "price")
    sms_count = blend_daily_metric(daily_sms, agora, hours, "count")
    sms_usage = blend_daily_metric(daily_sms, agora, hours, "usage")
    today_d = agora.strftime("%Y-%m-%d")
    recs_today = fetch_usage_records_url(sid, token, "", {"StartDate": today_d, "EndDate": today_d, "PageSize": 1000})
    aux = summarize(recs_today)
    return {
        "totalprice": totalprice,
        "sms_count": int(round(sms_count)),
        "sms_usage": int(round(sms_usage)),
        "sms_price": sms_price,
        "sum_price_all_but_totalprice": aux["sum_price_all_but_totalprice"],
        "categories": aux["categories"],
        "sms_sub_top": aux["sms_sub_top"],
    }


def summarize(records: list[dict]) -> dict:
    by_cat = {r.get("category", ""): r for r in records}
    totalprice_rec = by_cat.get("totalprice") or {}
    sms_rec = by_cat.get("sms") or {}
    all_price_except_total = 0.0
    sms_sub = []
    for r in records:
        cat = (r.get("category") or "").lower()
        p = parse_float(r.get("price"))
        if cat == "totalprice":
            continue
        all_price_except_total += p
        if cat.startswith("sms-") and cat != "sms":
            sms_sub.append(
                (
                    cat,
                    parse_int(r.get("count")),
                    parse_int(r.get("usage")),
                    p,
                )
            )
    sms_sub.sort(key=lambda x: -x[1])
    return {
        "totalprice": parse_float(totalprice_rec.get("price")),
        "sms_count": parse_int(sms_rec.get("count")),
        "sms_usage": parse_int(sms_rec.get("usage")),
        "sms_price": parse_float(sms_rec.get("price")),
        "sum_price_all_but_totalprice": all_price_except_total,
        "categories": len(records),
        "sms_sub_top": sms_sub[:12],
    }


def main():
    hours = float(os.getenv("USAGE_SNAPSHOT_HOURS", "24"))
    strategy = os.getenv("USAGE_DATE_STRATEGY", "rolling_24h_proxy").strip().lower()
    forced_day = (os.getenv("USAGE_UTC_DAY") or "").strip()
    pick = (os.getenv("TEST_USAGE_ACCOUNT") or "").strip().lower()
    write_csv = os.getenv("USAGE_WRITE_CSV", "").strip().lower() in ("1", "true", "yes")
    agora = utc_now()
    path_suffix = ""
    params: dict = {"PageSize": 1000}

    if forced_day:
        params["StartDate"] = forced_day
        params["EndDate"] = forced_day
        range_label = f"StartDate=EndDate={forced_day} UTC (USAGE_UTC_DAY)"
    elif strategy == "rolling_24h_proxy":
        range_label = (
            f"rolling_24h_proxy: Daily blend {hours:g}h UTC (~Account Insights Last 24h; uniforme/hora)"
        )
    elif strategy == "twilio_offsets":
        params["StartDate"] = "-1days"
        params["EndDate"] = agora.strftime("%Y-%m-%d")
        range_label = f"StartDate=-1days EndDate={params['EndDate']} (Twilio offsets)"
    elif strategy == "today_subresource":
        path_suffix = "/Today"
        range_label = "Usage/Records/Today.json (dia civil GMT corrente)"
    elif strategy == "end_utc_day":
        d = agora.strftime("%Y-%m-%d")
        params["StartDate"] = d
        params["EndDate"] = d
        range_label = f"StartDate=EndDate={d} UTC (dia civil atual; subestima Last 24h rolante na maior parte do dia)"
    elif strategy == "start_utc_day":
        d = (agora - timedelta(hours=hours)).strftime("%Y-%m-%d")
        params["StartDate"] = d
        params["EndDate"] = d
        range_label = f"StartDate=EndDate={d} UTC (so dia civil do inicio rolling)"
    else:
        # cover_days: todos os dias UTC tocados pela janela rolling (1 ou 2 dias completos na API)
        start_dt = agora - timedelta(hours=hours)
        start_d = start_dt.strftime("%Y-%m-%d")
        end_d = agora.strftime("%Y-%m-%d")
        params["StartDate"] = start_d
        params["EndDate"] = end_d
        range_label = f"StartDate={start_d} EndDate={end_d} UTC (cover_days; se 2 dias, soma ate ~48h faturada)"

    modo = f"USAGE_UTC_DAY={forced_day}" if forced_day else f"USAGE_DATE_STRATEGY={strategy}"
    print(f"# Usage Records (Billing API)\n- agora_utc: {agora.strftime('%Y-%m-%dT%H:%M:%SZ')}\n- {range_label}\n- {modo}\n")

    rows_out = []
    org_totalprice = 0.0
    org_sms_usage = 0
    org_sms_count = 0
    for acc in accounts_from_env():
        if not acc["sid"] or not acc["token"]:
            continue
        if pick and pick not in acc["nome"].lower():
            continue
        try:
            if strategy == "rolling_24h_proxy":
                s = blended_headline_billing(acc["sid"], acc["token"], agora, hours)
            else:
                recs = fetch_usage_records_url(acc["sid"], acc["token"], path_suffix, dict(params))
                s = summarize(recs)
        except Exception as e:
            print(f"**{acc['nome']}** ERRO: {e}\n")
            continue
        print(f"## {acc['nome']}")
        print(f"- Categorias devolvidas: {s['categories']}")
        print(f"- **totalprice (categoria totalprice) USD**: {s['totalprice']:.4f}")
        print(f"- **sms** (categoria agregada) count | usage | price USD: {s['sms_count']} | {s['sms_usage']} | {s['sms_price']:.4f}")
        print(f"- Soma price todas categorias exceto totalprice: {s['sum_price_all_but_totalprice']:.4f}")
        org_totalprice += s["totalprice"]
        org_sms_usage += s["sms_usage"]
        org_sms_count += s["sms_count"]
        if s["sms_sub_top"]:
            print("- Subcategorias sms-* (nao somar com `sms` — para debug):")
            for cat, c, u, p in s["sms_sub_top"][:12]:
                print(f"  - {cat}: count={c} usage={u} price={p:.4f}")
        print("")
        rows_out.append(
            {
                "Conta": acc["nome"],
                "Range": range_label,
                "TotalPrice_Totalprice": f"{s['totalprice']:.6f}",
                "SMS_Count": s["sms_count"],
                "SMS_Usage": s["sms_usage"],
                "SMS_Price": f"{s['sms_price']:.6f}",
                "Sum_Price_NoTotalprice": f"{s['sum_price_all_but_totalprice']:.6f}",
                "SMS_Subcategories_Sample": "|".join(f"{c}:{cnt}" for c, cnt, _, __ in s["sms_sub_top"][:5]),
                "Extraido_Utc": agora.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )

    if rows_out:
        print("## Soma todas as contas (aprox. vista master / org)")
        print(f"- totalprice somado: {org_totalprice:.4f} USD")
        print(f"- sms usage somado (segmentos/mensagens conforme Twilio): {org_sms_usage}")
        print(f"- sms count somado: {org_sms_count}")
        print("")
        rows_out.append(
            {
                "Conta": "__ORG_SUM__",
                "Range": range_label,
                "TotalPrice_Totalprice": f"{org_totalprice:.6f}",
                "SMS_Count": org_sms_count,
                "SMS_Usage": org_sms_usage,
                "SMS_Price": "",
                "Sum_Price_NoTotalprice": "",
                "SMS_Subcategories_Sample": "",
                "Extraido_Utc": agora.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )

    CSV_FIELDS = [
        "Conta",
        "Range",
        "TotalPrice_Totalprice",
        "SMS_Count",
        "SMS_Usage",
        "SMS_Price",
        "Sum_Price_NoTotalprice",
        "SMS_Subcategories_Sample",
        "Extraido_Utc",
    ]
    if write_csv and rows_out:
        path = os.path.join(ROOT, "conf_usage_billing_snapshot.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            w.writeheader()
            w.writerows(rows_out)
        print(f"CSV: {path}")

    print(
        "---\n"
        "Default rolling_24h_proxy: Daily + mistura por hora (~Last 24h Insights); nao e a mesma logica interna da consola.\n"
        "- Total Spend / SMS Spend: **TotalPrice_Totalprice** / **SMS_Price** (e SMS_Count / SMS_Usage para transacoes).\n"
        "- twilio_offsets soma **dois dias GMT completos** — em geral **acima** do card Last 24h.\n"
        "- USAGE_UTC_DAY forca um dia fixo. Export Twilio para conciliacao ao centimo."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
