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
  USAGE_START_DATE + USAGE_END_DATE — se ambos YYYY-MM-DD, intervalo inclusivo GMT (ex. mes da Usage Summary);
      tem precedencia sobre USAGE_UTC_DAY e USAGE_DATE_STRATEGY; agrega todas as linhas por categoria.
      Nesse modo os tres CSVs gravam-se em **month/** (nao sobrescrevem os ficheiros rolling na raiz do repo).
  TEST_USAGE_ACCOUNT — filtrar por nome (ex.: NS); vazio = todas com credenciais
  USAGE_WRITE_CSV — 1 grava conf_usage_billing_snapshot.csv, conf_usage_billing_by_category.csv e
      conf_usage_billing_daily.csv (serie diaria /Daily para visao geral).
  USAGE_WRITE_DAILY_CSV — 0 desliga so o CSV diario (default: 1 quando USAGE_WRITE_CSV=1).
  USAGE_DAILY_CATEGORIES — lista separada por virgulas (default: totalprice,sms) — categorias no endpoint Daily.
  USAGE_DAILY_MAX_SPAN_DAYS — maximo de dias no intervalo diario (default 366) para evitar jobs enormes.

Saida: totalprice (categoria totalprice), sms (count/usage/price). Para "SMS Transactions" na consola,
  testar **count** primeiro, depois **usage** (segmentos), conforme o card.
"""
from __future__ import annotations

import csv
import os
import sys
from collections import defaultdict
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


def clamp_date_range_gmt(start_d: str, end_d: str, max_days: int) -> tuple[str, str]:
    """Encurta end_d se o intervalo exceder max_days (inclusivo)."""
    a = datetime.strptime(start_d, "%Y-%m-%d").replace(tzinfo=timezone.utc).date()
    b = datetime.strptime(end_d, "%Y-%m-%d").replace(tzinfo=timezone.utc).date()
    if b < a:
        return start_d, start_d
    span = (b - a).days + 1
    if span <= max_days:
        return start_d, end_d
    nb = a + timedelta(days=max_days - 1)
    return start_d, nb.strftime("%Y-%m-%d")


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


def aggregate_usage_records(records: list[dict]) -> dict[str, dict[str, float | int]]:
    """Soma count/usage/price por categoria (Usage/Records)."""
    agg: dict[str, dict[str, float | int]] = defaultdict(lambda: {"count": 0, "usage": 0.0, "price": 0.0})
    for r in records:
        cat = (r.get("category") or "").strip()
        if not cat:
            continue
        a = agg[cat]
        a["count"] = int(a["count"]) + parse_int(r.get("count"))  # type: ignore[operator]
        a["usage"] = float(a["usage"]) + parse_float(r.get("usage"))
        a["price"] = float(a["price"]) + parse_float(r.get("price"))
    return dict(agg)


def summarize_aggregated(records: list[dict]) -> dict:
    """Agrega por categoria e devolve totais headline (sms, totalprice, etc.)."""
    agg = aggregate_usage_records(records)

    tp = agg.get("totalprice") or {"count": 0, "usage": 0.0, "price": 0.0}
    sm = agg.get("sms") or {"count": 0, "usage": 0.0, "price": 0.0}
    all_price_except_total = 0.0
    sms_sub: list[tuple[str, int, int, float]] = []
    for cat, v in agg.items():
        cl = cat.lower()
        p = float(v["price"])
        if cl == "totalprice":
            continue
        all_price_except_total += p
        if cl.startswith("sms-") and cl != "sms":
            sms_sub.append((cat, int(v["count"]), int(v["usage"]), p))
    sms_sub.sort(key=lambda x: -x[1])
    return {
        "totalprice": float(tp["price"]),
        "sms_count": int(sm["count"]),
        "sms_usage": int(sm["usage"]),
        "sms_price": float(sm["price"]),
        "sum_price_all_but_totalprice": all_price_except_total,
        "categories": len(agg),
        "sms_sub_top": sms_sub[:12],
    }


def summarize(records: list[dict]) -> dict:
    """Uma linha por categoria (ex. subresource Today); se houver duplicados, agrega."""
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        c = (r.get("category") or "").strip()
        if c:
            by_cat[c].append(r)
    if any(len(v) > 1 for v in by_cat.values()):
        return summarize_aggregated(records)
    by_one = {k: v[0] for k, v in by_cat.items()}
    totalprice_rec = by_one.get("totalprice") or {}
    sms_rec = by_one.get("sms") or {}
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
    write_daily = write_csv and os.getenv("USAGE_WRITE_DAILY_CSV", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )
    daily_cats = [c.strip() for c in (os.getenv("USAGE_DAILY_CATEGORIES") or "totalprice,sms").split(",") if c.strip()]
    agora = utc_now()
    path_suffix = ""
    params: dict = {"PageSize": 1000}
    start_e = (os.getenv("USAGE_START_DATE") or "").strip()
    end_e = (os.getenv("USAGE_END_DATE") or "").strip()
    fixed_range = len(start_e) == 10 and len(end_e) == 10 and start_e <= end_e

    if fixed_range:
        params["StartDate"] = start_e
        params["EndDate"] = end_e
        range_label = (
            f"StartDate={start_e} EndDate={end_e} UTC (USAGE_START_DATE/USAGE_END_DATE; "
            "agregado por categoria — alinhar com Usage Summary desse intervalo)"
        )
    elif forced_day:
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

    # Janela GMT YYYY-MM-DD para Usage/Records/Daily (graficos diarios — mesmo mes ou rolling).
    if fixed_range:
        daily_start_d, daily_end_d = start_e, end_e
    elif forced_day:
        daily_start_d, daily_end_d = forced_day, forced_day
    elif strategy == "rolling_24h_proxy":
        t0d = agora - timedelta(hours=hours)
        daily_start_d, daily_end_d = t0d.strftime("%Y-%m-%d"), agora.strftime("%Y-%m-%d")
    elif strategy == "today_subresource":
        ud = agora.strftime("%Y-%m-%d")
        daily_start_d, daily_end_d = ud, ud
    elif strategy == "twilio_offsets":
        daily_end_d = agora.strftime("%Y-%m-%d")
        daily_start_d = (agora - timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        sd0 = params.get("StartDate")
        ed0 = params.get("EndDate")
        if isinstance(sd0, str) and len(sd0) == 10 and sd0[:4].isdigit():
            daily_start_d, daily_end_d = sd0, ed0 or agora.strftime("%Y-%m-%d")
        else:
            t0d = agora - timedelta(hours=hours)
            daily_start_d, daily_end_d = t0d.strftime("%Y-%m-%d"), agora.strftime("%Y-%m-%d")

    max_span = int(os.getenv("USAGE_DAILY_MAX_SPAN_DAYS", "366"))
    d0, d1 = clamp_date_range_gmt(daily_start_d, daily_end_d, max_span)
    if (d0, d1) != (daily_start_d, daily_end_d):
        print(
            f"INFO daily CSV: intervalo {daily_start_d}..{daily_end_d} encolhido para {d0}..{d1} "
            f"(USAGE_DAILY_MAX_SPAN_DAYS={max_span})\n"
        )
        daily_start_d, daily_end_d = d0, d1

    if fixed_range:
        modo = f"USAGE_START_DATE={start_e} USAGE_END_DATE={end_e}"
    elif forced_day:
        modo = f"USAGE_UTC_DAY={forced_day}"
    else:
        modo = f"USAGE_DATE_STRATEGY={strategy}"
    print(f"# Usage Records (Billing API)\n- agora_utc: {agora.strftime('%Y-%m-%dT%H:%M:%SZ')}\n- {range_label}\n- {modo}\n")

    rows_out = []
    rows_by_cat: list[dict] = []
    rows_daily: list[dict] = []
    org_totalprice = 0.0
    org_sms_usage = 0
    org_sms_count = 0
    extraido = agora.strftime("%Y-%m-%dT%H:%M:%SZ")

    for acc in accounts_from_env():
        if not acc["sid"] or not acc["token"]:
            continue
        if pick and pick not in acc["nome"].lower():
            continue
        try:
            if strategy == "rolling_24h_proxy" and not fixed_range:
                s = blended_headline_billing(acc["sid"], acc["token"], agora, hours)
                t0 = agora - timedelta(hours=hours)
                start_d = t0.strftime("%Y-%m-%d")
                end_d = agora.strftime("%Y-%m-%d")
                recs = fetch_usage_records_url(
                    acc["sid"],
                    acc["token"],
                    "",
                    {"StartDate": start_d, "EndDate": end_d, "PageSize": 1000},
                )
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
        agg = aggregate_usage_records(recs)
        for cat in sorted(agg.keys(), key=lambda c: (-float(agg[c]["price"]), c)):
            v = agg[cat]
            u_raw = float(v["usage"])
            u_out: int | float = int(round(u_raw)) if abs(u_raw - round(u_raw)) < 1e-9 else round(u_raw, 4)
            rows_by_cat.append(
                {
                    "Conta": acc["nome"],
                    "Categoria": cat,
                    "Count": int(v["count"]),
                    "Usage": u_out,
                    "Price_USD": f"{float(v['price']):.6f}",
                    "Range": range_label,
                    "Extraido_Utc": extraido,
                }
            )
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
                "Extraido_Utc": extraido,
            }
        )
        if write_daily:
            for dcat in daily_cats:
                try:
                    drows = fetch_daily_category(acc["sid"], acc["token"], dcat, daily_start_d, daily_end_d)
                except Exception as e:
                    print(f"**{acc['nome']}** daily `{dcat}`: {e}\n")
                    continue
                for r in drows:
                    day = (r.get("start_date") or "")[:10]
                    if len(day) != 10:
                        continue
                    uraw = parse_float(r.get("usage"))
                    u_day: int | float = (
                        int(round(uraw)) if abs(uraw - round(uraw)) < 1e-9 else round(uraw, 4)
                    )
                    rows_daily.append(
                        {
                            "Conta": acc["nome"],
                            "Data_Utc": day,
                            "Categoria": dcat,
                            "Count": parse_int(r.get("count")),
                            "Usage": u_day,
                            "Price_USD": f"{parse_float(r.get('price')):.6f}",
                            "Range": range_label,
                            "Extraido_Utc": extraido,
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
                "Extraido_Utc": extraido,
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
    BY_CAT_FIELDS = ["Conta", "Categoria", "Count", "Usage", "Price_USD", "Range", "Extraido_Utc"]
    DAILY_FIELDS = ["Conta", "Data_Utc", "Categoria", "Count", "Usage", "Price_USD", "Range", "Extraido_Utc"]
    if write_csv and rows_out:
        if fixed_range:
            out_dir = os.path.join(ROOT, "month")
            os.makedirs(out_dir, exist_ok=True)
            dest_note = "month/ (intervalo fixo; coexiste com rolling na raiz)"
        else:
            out_dir = ROOT
            dest_note = "raiz do repo"
        path = os.path.join(out_dir, "conf_usage_billing_snapshot.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            w.writeheader()
            w.writerows(rows_out)
        print(f"CSV ({dest_note}): {path}")
        path_cat = os.path.join(out_dir, "conf_usage_billing_by_category.csv")
        with open(path_cat, "w", newline="", encoding="utf-8") as f:
            wc = csv.DictWriter(f, fieldnames=BY_CAT_FIELDS)
            wc.writeheader()
            wc.writerows(rows_by_cat)
        print(f"CSV ({dest_note}): {path_cat} ({len(rows_by_cat)} linhas)")
        if write_daily:
            path_day = os.path.join(out_dir, "conf_usage_billing_daily.csv")
            with open(path_day, "w", newline="", encoding="utf-8") as f:
                wd = csv.DictWriter(f, fieldnames=DAILY_FIELDS)
                wd.writeheader()
                wd.writerows(rows_daily)
            print(
                f"CSV ({dest_note}): {path_day} ({len(rows_daily)} linhas; "
                f"Daily {daily_start_d}..{daily_end_d} GMT; cats={daily_cats})"
            )

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
