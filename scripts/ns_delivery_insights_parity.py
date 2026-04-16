"""
Paridade NS com Twilio Console: SMS > Insights > Delivery & Errors (Past N h).

Delega a logica em scripts/fetch_delivery_insights_snapshot.py (collect_insights_for_account).

Env: RECUPERACAO_NS_SID, RECUPERACAO_NS_TOKEN
Env opcional: DELIVERY_INSIGHTS_HOURS (default 4), NS_INSIGHTS_LIST_MODE (default activity),
  DELIVERY_INSIGHTS_MAX_PAGES, DELIVERY_INSIGHTS_STOP_EMPTY
"""
from __future__ import annotations

import importlib.util
import os
import sys
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(ROOT, ".env"))


def _load_fetch_mod():
    p = os.path.join(ROOT, "scripts", "fetch_delivery_insights_snapshot.py")
    spec = importlib.util.spec_from_file_location("_insights_snap", p)
    if spec is None or spec.loader is None:
        raise RuntimeError("importlib: spec invalido")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def utc_now():
    return datetime.now(timezone.utc)


def main() -> int:
    sid = (os.getenv("RECUPERACAO_NS_SID") or "").strip()
    token = (os.getenv("RECUPERACAO_NS_TOKEN") or "").strip()
    if not sid or not token:
        print("Defina RECUPERACAO_NS_SID e RECUPERACAO_NS_TOKEN no .env.", file=sys.stderr)
        return 1

    hours = float(os.getenv("DELIVERY_INSIGHTS_HOURS", "4"))
    list_mode = (os.getenv("NS_INSIGHTS_LIST_MODE") or "activity").strip().lower()
    max_pages = int(os.getenv("DELIVERY_INSIGHTS_MAX_PAGES", "150"))
    stop_empty = int(os.getenv("DELIVERY_INSIGHTS_STOP_EMPTY", "5"))
    direction = (os.getenv("DELIVERY_DIRECTION") or "outbound").strip().lower()
    if direction not in ("outbound", "all"):
        direction = "outbound"

    agora = utc_now()
    since_dt = agora - timedelta(hours=hours)
    mod = _load_fetch_mod()
    r = mod.collect_insights_for_account(
        sid, token, "NS", "Recuperação", agora, since_dt, list_mode, max_pages, stop_empty, direction
    )
    ins = r["insight_five"]
    sm = r["stats_msg"]

    print("=" * 72)
    print("NS — API Messages (paridade Delivery & Errors / Outgoing)")
    print("=" * 72)
    print(f"Janela UTC:     ultimas {hours:g} h  [{since_dt.strftime('%Y-%m-%dT%H:%M:%SZ')} .. {agora.strftime('%Y-%m-%dT%H:%M:%SZ')}]")
    print(f"List mode:      {list_mode}")
    print(f"API pages:      {r['api_pages']}" + ("  (CAP)" if r["api_pages_capped"] else ""))
    print()
    print("--- Legenda 5 estados (contagens por MENSAGEM) ---")
    print(f"  Delivered:         {ins['Delivered']}")
    print(f"  Failed:            {ins['Failed']}")
    print(f"  Undelivered:       {ins['Undelivered']}")
    print(f"  Sent:              {ins['Sent']}")
    print(f"  Delivery Unknown:  {ins['Delivery_Unknown']}")
    print(f"  --- Total:         {sum(ins.values())}  (msgs classificadas: {sm['Total']})")
    print()
    print("Para gerar CSV de todas as contas: python scripts/fetch_delivery_insights_snapshot.py (com DELIVERY_INSIGHTS_WRITE_CSV=1)")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
