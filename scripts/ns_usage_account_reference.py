"""
Referencia Twilio — so conta NS (Recuperacao).

Chama:
  - GET .../Accounts/{AccountSid}.json (metadados da conta; ver docs IAM / Account)
  - GET .../Accounts/{AccountSid}/Usage/Records.json (Usage Records)
  - Opcional: .../Usage/Records/Today.json

Docs:
  https://www.twilio.com/docs/usage/api/usage-record
  https://www.twilio.com/docs/iam/api/account

Env (raiz do repo, ficheiro .env):
  RECUPERACAO_NS_SID, RECUPERACAO_NS_TOKEN

Env opcional:
  USAGE_UTC_DAY — AAAA-MM-DD forca StartDate=EndDate
  USAGE_DATE_STRATEGY — rolling_24h_proxy | twilio_offsets | end_utc_day | today_subresource (default: rolling_24h_proxy)
  NS_USAGE_INCLUDE_TODAY — 1 para GET extra em /Usage/Records/Today.json

Uso:
  python scripts/ns_usage_account_reference.py              # tabela no ecra (comparar com consola)
  python scripts/ns_usage_account_reference.py --json     # dump JSON completo
"""
from __future__ import annotations

import argparse
import json
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


def mask(s: str | None, keep: int = 6) -> str:
    if not s:
        return "(vazio)"
    s = str(s)
    if len(s) <= keep:
        return "***"
    return s[:keep] + "…" + s[-4:]


def get_json(session: requests.Session, url: str, params: dict | None = None) -> dict:
    r = session.get(url, params=params or {}, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code} {url}\n{r.text[:800]}")
    return r.json()


def fetch_usage_records_all_pages(session: requests.Session, base_path: str, params: dict) -> list[dict]:
    """base_path: '' ou '/Today'. Acumula usage_records de todas as paginas."""
    out: list[dict] = []
    sid = session.auth.username  # type: ignore[attr-defined]
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Usage/Records{base_path}.json"
    p = dict(params)
    while url:
        body = get_json(session, url, p)
        out.extend(body.get("usage_records", []))
        nxt = body.get("next_page_uri")
        url = f"https://api.twilio.com{nxt}" if nxt else None
        p = {}
    return out


def print_compare_table(captured: dict, acc: dict, highlights: dict[str, dict | None]) -> None:
    """Saida legivel para comparar com Twilio Console (Account / Usage)."""
    print("=" * 72)
    print("NS (RECUPERACAO) — Twilio API (comparar com a conta na consola)")
    print("=" * 72)
    print(f"Agora UTC:        {captured.get('agora_utc', '')}")
    print(f"Janela Usage:    {captured.get('usage_range_label', '')}")
    print(f"Pedido:          {captured.get('usage_query', {})}")
    print(f"Credenciais:     SID {captured.get('env_sid_masked')} | Token {captured.get('env_token_masked')}")
    print()
    print("--- Account GET .../Accounts/{Sid}.json ---")
    print(f"  sid             {acc.get('sid', '')}")
    print(f"  friendly_name   {acc.get('friendly_name', '')}")
    print(f"  status          {acc.get('status', '')}")
    print(f"  type            {acc.get('type', '')}")
    print(f"  date_created    {acc.get('date_created', '')}")
    print(f"  date_updated    {acc.get('date_updated', '')}")
    print(f"  owner_account_sid {acc.get('owner_account_sid', '')}")
    print()
    print("--- Usage Records (categorias em destaque) ---")
    hdr = f"{'category':<18} {'count':>10} {'usage':>12} {'price_usd':>12}  start_date   end_date     as_of"
    print(hdr)
    print("-" * len(hdr))
    for name in ("totalprice", "sms", "sms-outbound", "sms-inbound"):
        r = highlights.get(name)
        if not r:
            print(f"{name:<18} {'(sem registo)':>10}")
            continue
        cat = (r.get("category") or name)[:18]
        cnt = r.get("count") if r.get("count") is not None else ""
        usg = r.get("usage") if r.get("usage") is not None else ""
        prc = r.get("price") if r.get("price") is not None else ""
        print(
            f"{cat:<18} {str(cnt):>10} {str(usg):>12} {str(prc):>12}  "
            f"{r.get('start_date', '') or '':12} {r.get('end_date', '') or '':12} {r.get('as_of', '') or ''}"
        )
    print()
    n = captured.get("usage_record_count", 0)
    print(f"(Total de linhas category neste pedido: {n}. Use --json para lista completa.)")
    print("=" * 72)


def main() -> int:
    ap = argparse.ArgumentParser(description="NS account + Usage Records (referencia Twilio)")
    ap.add_argument("--json", action="store_true", help="Dump JSON completo (para ficheiro / debug)")
    args = ap.parse_args()

    sid = (os.getenv("RECUPERACAO_NS_SID") or "").strip()
    token = (os.getenv("RECUPERACAO_NS_TOKEN") or "").strip()
    if not sid or not token:
        print("Defina RECUPERACAO_NS_SID e RECUPERACAO_NS_TOKEN no .env na raiz do repo.", file=sys.stderr)
        return 1

    session = requests.Session()
    session.auth = HTTPBasicAuth(sid, token)

    agora = utc_now()
    forced_day = (os.getenv("USAGE_UTC_DAY") or "").strip()
    strategy = (os.getenv("USAGE_DATE_STRATEGY") or "rolling_24h_proxy").strip().lower()
    include_today = os.getenv("NS_USAGE_INCLUDE_TODAY", "").strip().lower() in ("1", "true", "yes")
    hours = float(os.getenv("USAGE_SNAPSHOT_HOURS", "24"))

    params: dict = {"PageSize": 1000}
    range_label = ""
    if forced_day:
        params["StartDate"] = forced_day
        params["EndDate"] = forced_day
        range_label = f"StartDate=EndDate={forced_day} (USAGE_UTC_DAY)"
    elif strategy == "rolling_24h_proxy":
        range_label = f"rolling_24h_proxy: Daily blend {hours:g}h UTC (~Account Insights Last 24h)"
    elif strategy == "twilio_offsets":
        params["StartDate"] = "-1days"
        params["EndDate"] = agora.strftime("%Y-%m-%d")
        range_label = f"StartDate=-1days EndDate={params['EndDate']} (twilio_offsets)"
    elif strategy == "today_subresource":
        range_label = "subresource Today.json (dia civil GMT corrente)"
    elif strategy == "end_utc_day":
        d = agora.strftime("%Y-%m-%d")
        params["StartDate"] = d
        params["EndDate"] = d
        range_label = f"StartDate=EndDate={d} (end_utc_day)"
    elif strategy == "start_utc_day":
        d = (agora - timedelta(hours=hours)).strftime("%Y-%m-%d")
        params["StartDate"] = d
        params["EndDate"] = d
        range_label = f"StartDate=EndDate={d} (start_utc_day)"
    else:
        # cover_days
        start_dt = agora - timedelta(hours=hours)
        start_d = start_dt.strftime("%Y-%m-%d")
        end_d = agora.strftime("%Y-%m-%d")
        params["StartDate"] = start_d
        params["EndDate"] = end_d
        range_label = f"StartDate={start_d} EndDate={end_d} (cover_days)"

    captured: dict = {
        "conta": "NS",
        "env_sid_masked": mask(sid),
        "env_token_masked": mask(token),
        "agora_utc": agora.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "usage_range_label": range_label,
    }

    # --- Account (2010-04-01) ---
    acc_url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}.json"
    acc = get_json(session, acc_url)
    acc_safe = {k: v for k, v in acc.items() if k != "auth_token"}
    acc_safe["auth_token"] = "***REDACTED***" if acc.get("auth_token") else None
    captured["account_resource"] = acc_safe
    captured["account_top_level_keys"] = sorted(acc.keys())

    # --- Usage Records (lista principal) ou blend ~Last 24h ---
    highlights: dict
    records: list[dict]
    if strategy == "rolling_24h_proxy":
        import importlib.util

        mod_path = os.path.join(ROOT, "scripts", "fetch_usage_billing_snapshot.py")
        spec = importlib.util.spec_from_file_location("_twilio_usage_billing", mod_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("importlib spec invalido")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        bl = mod.blended_headline_billing(sid, token, agora, hours)
        captured["usage_query"] = {"mode": "rolling_24h_proxy", "hours": hours}
        captured["usage_blended_headline"] = bl
        records = []
        captured["usage_record_count"] = 0
        captured["usage_categories"] = []
        captured["usage_record_field_names_union"] = []
        ts = captured["agora_utc"]
        highlights = {
            "totalprice": {
                "category": "totalprice",
                "count": "",
                "usage": f"{bl['totalprice']:.5f}",
                "price": f"{bl['totalprice']:.5f}",
                "start_date": "~blend",
                "end_date": "~blend",
                "as_of": ts,
            },
            "sms": {
                "category": "sms",
                "count": str(bl["sms_count"]),
                "usage": str(bl["sms_usage"]),
                "price": f"{bl['sms_price']:.5f}",
                "start_date": "~blend",
                "end_date": "~blend",
                "as_of": ts,
            },
            "sms-outbound": None,
            "sms-inbound": None,
        }
        captured["usage_highlights"] = highlights
    else:
        if strategy == "today_subresource":
            usage_path = "/Today"
            usage_params: dict = {"PageSize": 1000}
        else:
            usage_path = ""
            usage_params = params
        captured["usage_query"] = {"path_suffix": usage_path or "/", "params": usage_params}
        records = fetch_usage_records_all_pages(session, usage_path, usage_params)
        captured["usage_record_count"] = len(records)
        captured["usage_categories"] = sorted(
            {c for r in records if (c := (r.get("category") or "").strip()) and c != "category"}
        )

        key_union: set[str] = set()
        for r in records[:500]:
            key_union.update(r.keys())
        captured["usage_record_field_names_union"] = sorted(key_union)

        def pick(cat: str) -> dict | None:
            for r in records:
                if (r.get("category") or "") == cat:
                    return r
            return None

        highlights = {
            "totalprice": pick("totalprice"),
            "sms": pick("sms"),
            "sms-outbound": pick("sms-outbound"),
            "sms-inbound": pick("sms-inbound"),
        }
        captured["usage_highlights"] = highlights

    today_records: list[dict] = []
    if include_today and strategy != "today_subresource":
        today_records = fetch_usage_records_all_pages(session, "/Today", {"PageSize": 1000})
    captured["usage_today_subresource_count"] = len(today_records)
    if today_records:
        captured["usage_today_highlights"] = {
            "totalprice": next((r for r in today_records if r.get("category") == "totalprice"), None),
            "sms": next((r for r in today_records if r.get("category") == "sms"), None),
        }

    if args.json:
        print(json.dumps(captured, indent=2, ensure_ascii=False))
    else:
        print_compare_table(captured, acc, highlights)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
