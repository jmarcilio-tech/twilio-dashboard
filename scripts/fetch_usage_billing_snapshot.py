"""
Snapshot de billing via API oficial Twilio Usage Records (proximo de Account Insights).

Documentacao: https://www.twilio.com/docs/usage/api/usage-record

Limitacao: StartDate/EndDate sao em GMT YYYY-MM-DD (granularidade diaria na maioria dos casos).
A consola "Last 24 hours" e uma janela rolante; este script cobre os dias civis UTC que
intersectam as ultimas N horas (pode diferir ligeiramente do card da consola).

Env:
  USAGE_SNAPSHOT_HOURS — default 24 (so usado em cover_days)
  USAGE_DATE_STRATEGY —
      cover_days — dias civis UTC que intersectam [agora-hours, agora] (2 dias = soma GRANDE; diverge da consola).
      end_utc_day — StartDate=EndDate=dia UTC de agora (um dia; muitas vezes mais perto do card "Last 24h" a tarde/noite UTC).
      start_utc_day — so o dia UTC em que comecou a janela rolling (um dia).
      twilio_offsets — StartDate=-1days EndDate=today (interpretacao Twilio).
      today_subresource — GET .../Usage/Records/Today.json (agregado "hoje GMT" so; pode bater se a consola estiver alinhada a isso).
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
    strategy = os.getenv("USAGE_DATE_STRATEGY", "end_utc_day").strip().lower()
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
        range_label = f"StartDate=EndDate={d} UTC (so dia civil atual; recomendado vs Last24h na consola)"
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
        "---\nBilling 'Last 24 hours' na consola e rolante; a API Usage so aceita dias GMT (StartDate/EndDate).\n"
        "- end_utc_day: so dia civil UTC atual — costuma aproximar **Total Spend**; para SMS Transactions compare **usage** (segmentos) com o card.\n"
        "- cover_days / twilio_offsets: intervalo mais largo — infla totais vs 'Last 24h'.\n"
        "- Para bater ao minuto com a consola, use export oficial ou alinhe o filtro da consola a **um dia UTC** e use USAGE_UTC_DAY=AAAA-MM-DD."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
