import json
import os
import csv
import concurrent.futures
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

load_dotenv()

# --- Constantes / ficheiros ---
csv_stats = "conf_delivery_stats.csv"
csv_horario = "conf_delivery_horario.csv"
csv_stats_history = os.getenv("DELIVERY_STATS_HISTORY_FILE", "conf_delivery_stats_history.csv")
STATE_PATH = os.getenv("DELIVERY_STATE_FILE", "delivery_sync_state.json")
# outbound = só saída (Messaging Insights com Outgoing). all = todas as direções (legado).
DELIVERY_DIRECTION = os.getenv("DELIVERY_DIRECTION", "outbound").strip().lower()
if DELIVERY_DIRECTION not in ("outbound", "all"):
    DELIVERY_DIRECTION = "outbound"

# Lista Messages: sent = DateSent> (rápido, igual à Twilio list API). activity = sem filtro na API,
# inclui outbound se date_sent OU date_created cair na janela (aproxima Messaging Insights; mais páginas).
# baseline_mes + activity reverte automaticamente para sent (paginação excessiva).
DELIVERY_LIST_MODE = os.getenv("DELIVERY_LIST_MODE", "sent").strip().lower()
if DELIVERY_LIST_MODE not in ("sent", "activity"):
    DELIVERY_LIST_MODE = "sent"

# Categorias alinhadas ao painel "Total Outgoing Messages" (Delivery & Errors)
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


def empty_bucket():
    return {k: 0 for k in CATEGORIAS}


def mensagem_conta_para_extracao(m: dict) -> bool:
    """True se a mensagem entra na soma (alinhado ao filtro Outgoing da consola)."""
    if DELIVERY_DIRECTION == "all":
        return True
    d = (m.get("direction") or "").strip().lower()
    # Twilio: inbound | outbound-api | outbound-call | outbound-reply
    return d.startswith("outbound")


def parse_twilio_dt(s: str):
    if not s or not str(s).strip():
        return None
    try:
        return parsedate_to_datetime(s.strip())
    except Exception:
        return None


def in_activity_time_window(m: dict, since_dt: datetime, until_dt: datetime) -> bool:
    dc = parse_twilio_dt(m.get("date_created") or "")
    ds = parse_twilio_dt(m.get("date_sent") or "")
    in_c = dc is not None and since_dt <= dc <= until_dt
    in_s = ds is not None and since_dt <= ds <= until_dt
    return in_c or in_s


def insight_five_from_msg_stats(stats_msg: dict) -> dict:
    """5 buckets da legenda Delivery & Errors (contagem por mensagem, não segmentos)."""
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
    # "Delivery unknown" no painel: estados não mapeados / reporting / inbound API
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


def inicio_mes_utc(dt: datetime) -> datetime:
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def load_state():
    if not os.path.exists(STATE_PATH):
        return {}
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(data: dict):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def migrar_horario_se_schema_antigo():
    if not os.path.exists(csv_horario):
        return
    with open(csv_horario, encoding="utf-8") as f:
        header = f.readline()
    if "Delivery_Unknown" in header and "Accepted" in header:
        return
    legacy = csv_horario.replace(".csv", "_legacy.csv")
    if not os.path.exists(legacy):
        os.rename(csv_horario, legacy)
        print(f"📦 Cabeçalho antigo de horário: renomeado para {legacy} (novo schema).")


def slot_15min(dt_str):
    if not dt_str:
        return None
    try:
        dt = parsedate_to_datetime(dt_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        minuto_slot = (dt.minute // 15) * 15
        return dt.strftime(f"%Y-%m-%d %H:{minuto_slot:02d}")
    except Exception:
        return None


def carregar_chaves_existentes(filepath, key_cols):
    chaves = set()
    if not os.path.exists(filepath):
        return chaves
    with open(filepath, encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if row:
                chaves.add(tuple(row[i] for i in key_cols))
    return chaves


def montar_linha_stats(
    r: dict,
    janela_lbl: str,
    fetch_md: str,
    extraido: str,
    agregado_ate_utc: str,
    github_run_id: str,
) -> list:
    """Uma linha do CSV de stats (mesmo schema que conf_delivery_stats.csv)."""
    ins = insight_five_from_msg_stats(r["stats_msg"])
    ins_total = sum(ins.values())
    row = [
        r["nome"],
        r["cat"],
        janela_lbl,
        fetch_md,
        DELIVERY_DIRECTION,
        DELIVERY_LIST_MODE,
        r["stats_msg"]["Total"],
        r["stats_seg"]["Total"],
    ]
    for c in CATEGORIAS:
        row.append(r["stats_seg"][c])
    row.append(r["taxa"])
    row.extend(
        [
            ins["Delivered"],
            ins["Failed"],
            ins["Delivery_Unknown"],
            ins["Undelivered"],
            ins["Sent"],
            ins_total,
        ]
    )
    row.append(r.get("api_pages", 0))
    row.append(1 if r.get("api_pages_capped") else 0)
    row.append(agregado_ate_utc)
    row.append(github_run_id or "")
    row.append(extraido)
    return row


accounts = [
    {"sid": os.getenv("RECUPERACAO_NS_SID"), "token": os.getenv("RECUPERACAO_NS_TOKEN"), "nome": "NS", "categoria": "Recuperação"},
    {"sid": os.getenv("BROADCAST_JOAO_SID"), "token": os.getenv("BROADCAST_JOAO_TOKEN"), "nome": "Joao", "categoria": "Broadcast"},
    {"sid": os.getenv("BROADCAST_BERNARDO_SID"), "token": os.getenv("BROADCAST_BERNARDO_TOKEN"), "nome": "Bernardo", "categoria": "Broadcast"},
    {"sid": os.getenv("BROADCAST_RAFA_SID"), "token": os.getenv("BROADCAST_RAFA_TOKEN"), "nome": "Rafa", "categoria": "Broadcast"},
    {"sid": os.getenv("STANDBY_HAVEN_SID"), "token": os.getenv("STANDBY_HAVEN_TOKEN"), "nome": "Havenmove", "categoria": "Standby"},
    {"sid": os.getenv("STANDBY_REHABLEAF_SID"), "token": os.getenv("STANDBY_REHABLEAF_TOKEN"), "nome": "Rehableaf", "categoria": "Standby"},
    {"sid": os.getenv("STANDBY_RICHARD_SID"), "token": os.getenv("STANDBY_RICHARD_TOKEN"), "nome": "Richard", "categoria": "Standby"},
    {"sid": os.getenv("STANDBY_NATUREMOVE_SID"), "token": os.getenv("STANDBY_NATUREMOVE_TOKEN"), "nome": "Naturemove", "categoria": "Standby"},
]

AGORA = utc_now()
JANELA_HORAS = float(os.getenv("DELIVERY_JANELA_HORAS", "0.0833333333"))
FETCH_MODE_RAW = os.getenv("DELIVERY_FETCH_MODE", "incremental").strip().lower()
state = load_state()
cur_month = AGORA.strftime("%Y-%m")

if FETCH_MODE_RAW == "auto":
    if state.get("baseline_month") == cur_month:
        FETCH_MODE = "incremental"
    else:
        FETCH_MODE = "baseline_mes"
else:
    FETCH_MODE = FETCH_MODE_RAW

if FETCH_MODE not in ("incremental", "baseline_mes", "baseline_24h"):
    FETCH_MODE = "incremental"

DELIVERY_WINDOW_PRESET = os.getenv("DELIVERY_WINDOW_PRESET", "janela_horas").strip().lower()
if DELIVERY_WINDOW_PRESET not in ("janela_horas", "since_yesterday_utc"):
    DELIVERY_WINDOW_PRESET = "janela_horas"

if FETCH_MODE == "incremental":
    if DELIVERY_WINDOW_PRESET == "since_yesterday_utc":
        yd = AGORA.date() - timedelta(days=1)
        since_dt = datetime(yd.year, yd.month, yd.day, 0, 0, 0, tzinfo=timezone.utc)
        JANELA_LABEL = f"since_yesterday_utc_{since_dt.strftime('%Y-%m-%d')}"
    else:
        since_dt = AGORA - timedelta(hours=JANELA_HORAS)
        JANELA_LABEL = f"{int(JANELA_HORAS * 60)}min" if JANELA_HORAS < 1 else f"{int(JANELA_HORAS)}h"
elif FETCH_MODE == "baseline_mes":
    since_dt = inicio_mes_utc(AGORA)
    JANELA_LABEL = f"baseline_mes_{cur_month}"
else:  # baseline_24h
    since_dt = AGORA - timedelta(hours=24)
    JANELA_LABEL = "baseline_24h"

FILTRO_INICIO = since_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

if DELIVERY_WINDOW_PRESET == "since_yesterday_utc" and FETCH_MODE != "incremental":
    print(
        "INFO DELIVERY_WINDOW_PRESET=since_yesterday_utc so vale em FETCH_MODE=incremental; "
        "nesta execucao o inicio da janela segue o modo baseline escolhido."
    )

if DELIVERY_LIST_MODE == "activity" and FETCH_MODE == "baseline_mes":
    print("⚠️ DELIVERY_LIST_MODE=activity incompatível com baseline_mes — a usar sent.")
    DELIVERY_LIST_MODE = "sent"

DELIVERY_ACTIVITY_MAX_PAGES = int(os.getenv("DELIVERY_ACTIVITY_MAX_PAGES", "80"))
DELIVERY_ACTIVITY_STOP_EMPTY = int(os.getenv("DELIVERY_ACTIVITY_STOP_EMPTY", "5"))


def _agrega_mensagem(m: dict, stats_msg: dict, stats_seg: dict, horario: dict):
    status = m.get("status", "unknown")
    chave = classificar_status(status)
    sent_at = m.get("date_sent") or m.get("date_created", "")
    slot = slot_15min(sent_at)
    segments = int(m.get("num_segments", 1) or 1)
    stats_msg["Total"] += 1
    stats_seg["Total"] += segments
    stats_msg[chave] += 1
    stats_seg[chave] += segments
    if slot:
        if slot not in horario:
            horario[slot] = empty_bucket()
        horario[slot][chave] += segments


def processar_conta(acc):
    sid, token, nome, cat = acc["sid"], acc["token"], acc["nome"], acc["categoria"]
    if not sid or not token:
        return None

    session = requests.Session()
    session.auth = HTTPBasicAuth(sid, token)

    stats_msg = empty_stats()
    stats_seg = empty_stats()
    horario = {}
    api_ok = False

    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    pagina = 0
    consecutive_empty = 0
    api_pages_capped = False

    if DELIVERY_LIST_MODE == "sent":
        params = {"DateSent>": FILTRO_INICIO, "PageSize": 1000}
    else:
        params = {"PageSize": 1000}

    while url:
        try:
            if DELIVERY_LIST_MODE == "activity" and pagina >= DELIVERY_ACTIVITY_MAX_PAGES:
                print(f"⚠️ {nome}: activity atingiu DELIVERY_ACTIVITY_MAX_PAGES={DELIVERY_ACTIVITY_MAX_PAGES}")
                api_pages_capped = True
                break
            r = session.get(url, params=params, timeout=60)
            if r.status_code != 200:
                print(f"⚠️ {nome}: HTTP {r.status_code}")
                break
            api_ok = True
            body = r.json()
            pagina += 1
            if pagina % 50 == 0:
                print(f"… {nome}: página {pagina}")

            in_page = 0
            for m in body.get("messages", []):
                if not mensagem_conta_para_extracao(m):
                    continue
                if DELIVERY_LIST_MODE == "activity":
                    if not in_activity_time_window(m, since_dt, AGORA):
                        continue
                    in_page += 1
                _agrega_mensagem(m, stats_msg, stats_seg, horario)

            if DELIVERY_LIST_MODE == "activity":
                if in_page == 0:
                    consecutive_empty += 1
                    if consecutive_empty >= DELIVERY_ACTIVITY_STOP_EMPTY:
                        break
                else:
                    consecutive_empty = 0

            next_uri = body.get("next_page_uri")
            url = f"https://api.twilio.com{next_uri}" if next_uri else None
            params = {}
        except Exception as e:
            print(f"❌ Falha em {nome}: {e}")
            break

    taxa = round((stats_seg["Delivered"] / stats_seg["Total"] * 100), 2) if stats_seg["Total"] > 0 else 0.0
    cap_hint = " (cap!)" if api_pages_capped else ""
    print(f"✅ {nome} [{cat}] — {stats_msg['Total']} msgs | {stats_seg['Total']} segmentos | {taxa}% entregues | API páginas={pagina}{cap_hint}")
    return {
        "nome": nome,
        "cat": cat,
        "stats_msg": stats_msg,
        "stats_seg": stats_seg,
        "taxa": taxa,
        "horario": horario,
        "api_ok": api_ok,
        "api_pages": pagina,
        "api_pages_capped": api_pages_capped,
    }


migrar_horario_se_schema_antigo()

print(
    f"🚀 Delivery | modo={FETCH_MODE} | janela_preset={DELIVERY_WINDOW_PRESET} | lista={DELIVERY_LIST_MODE} | "
    f"direção={DELIVERY_DIRECTION} | janela_label={JANELA_LABEL} | "
    f"DateSent>={FILTRO_INICIO} UTC | agora={AGORA.strftime('%Y-%m-%dT%H:%M:%SZ')} | {len(accounts)} contas"
)
if DELIVERY_WINDOW_PRESET == "since_yesterday_utc" and FETCH_MODE == "incremental":
    print(
        f"INFO Varredura: desde 00:00 UTC de ontem ({since_dt.strftime('%Y-%m-%d')}) ate agora — "
        "comparar com Twilio Insights em UTC; subir DELIVERY_ACTIVITY_MAX_PAGES se usar lista=activity."
    )

# activity pagina mais por conta: menos workers em paralelo para reduzir 429 / timeout.
_max_workers = 3 if DELIVERY_LIST_MODE == "activity" else 8
with concurrent.futures.ThreadPoolExecutor(max_workers=_max_workers) as executor:
    resultados_raw = list(executor.map(processar_conta, accounts))
resultados_raw = [r for r in resultados_raw if r is not None]
# CSV stats: uma linha por conta com credenciais (volume 0 incluído — Api_Pages e capped visíveis).
alguma_api_ok = any(r.get("api_ok") for r in resultados_raw)

EXTRAIDO_EM = AGORA.strftime("%Y-%m-%d %H:%M UTC")
AGREGADO_ATE_UTC = AGORA.strftime("%Y-%m-%dT%H:%M:%SZ")
GITHUB_RUN_ID = os.getenv("GITHUB_RUN_ID", "").strip()
WRITE_STATS_SNAPSHOT = os.getenv("DELIVERY_STATS_WRITE_SNAPSHOT", "1").strip().lower() not in ("0", "false", "no")
SKIP_HORARIO = os.getenv("DELIVERY_SKIP_HORARIO", "").strip().lower() in ("1", "true", "yes")

# --- conf_delivery_stats.csv ---
INSIGHT_MSG_COLS = [
    "Insight_Delivered_Msgs",
    "Insight_Failed_Msgs",
    "Insight_Delivery_Unknown_Msgs",
    "Insight_Undelivered_Msgs",
    "Insight_Sent_Msgs",
    "Insight_Total_Msgs",
]
header_stats = (
    ["Conta", "Categoria", "Janela", "Modo", "Direcao", "List_Mode", "Mensagens", "Segmentos"]
    + CATEGORIAS
    + ["Taxa_Entrega_%"]
    + INSIGHT_MSG_COLS
    + ["Api_Pages", "Api_Pages_Capped"]
    + ["Agregado_Ate_Utc", "Github_Run_Id", "Extraido_Em"]
)
if WRITE_STATS_SNAPSHOT:
    resultados_ordenados = sorted(resultados_raw, key=lambda x: x.get("nome", ""))
    with open(csv_stats, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header_stats)
        for r in resultados_ordenados:
            w.writerow(
                montar_linha_stats(r, JANELA_LABEL, FETCH_MODE, EXTRAIDO_EM, AGREGADO_ATE_UTC, GITHUB_RUN_ID)
            )
    print(f"📄 {csv_stats} — {len(resultados_raw)} linha(s) (todas as contas com credenciais), segmentos por categoria no dash")
else:
    print(f"(omitido escrita) {csv_stats} — DELIVERY_STATS_WRITE_SNAPSHOT=0 (mantém snapshot do job rápido)")

APPEND_STATS_HISTORY = os.getenv("DELIVERY_APPEND_STATS_HISTORY", "").strip().lower() in ("1", "true", "yes")
if APPEND_STATS_HISTORY:
    precisa_header_hist = (not os.path.exists(csv_stats_history)) or os.path.getsize(csv_stats_history) == 0
    with open(csv_stats_history, "a", newline="", encoding="utf-8") as hf:
        hw = csv.writer(hf)
        if precisa_header_hist:
            hw.writerow(header_stats)
        for r in sorted(resultados_raw, key=lambda x: x.get("nome", "")):
            hw.writerow(
                montar_linha_stats(r, JANELA_LABEL, FETCH_MODE, EXTRAIDO_EM, AGREGADO_ATE_UTC, GITHUB_RUN_ID)
            )
    print(f"📄 {csv_stats_history} — append {len(resultados_raw)} linha(s) (histórico para série temporal / DB)")

# --- conf_delivery_horario.csv (append) ---
novas_horario = []
if not SKIP_HORARIO:
    chaves_horario = carregar_chaves_existentes(csv_horario, key_cols=[0, 1])
    for r in resultados_raw:
        if r["stats_seg"]["Total"] <= 0:
            continue
        for slot, b in r["horario"].items():
            if (slot, r["nome"]) not in chaves_horario:
                row = [slot, r["nome"], r["cat"]]
                for c in CATEGORIAS:
                    row.append(b[c])
                row.append(sum(b[c] for c in CATEGORIAS))
                novas_horario.append(row)

    escrever_header = not os.path.exists(csv_horario)
    with open(csv_horario, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if escrever_header:
            w.writerow(["Slot_15min", "Conta", "Categoria"] + CATEGORIAS + ["Total_Slot"])
        w.writerows(novas_horario)
    print(f"📄 {csv_horario} — {len(novas_horario)} slot(s) novo(s)")
else:
    print(f"(omitido) {csv_horario} — DELIVERY_SKIP_HORARIO=1")

# --- Estado (auto: baseline mensal uma vez por mês; depois incremental rápido) ---
new_state = dict(state)
new_state["last_run_utc"] = AGORA.strftime("%Y-%m-%dT%H:%M:%SZ")
new_state["last_fetch_mode"] = FETCH_MODE
new_state["delivery_direction"] = DELIVERY_DIRECTION
new_state["delivery_list_mode"] = DELIVERY_LIST_MODE
new_state["delivery_window_preset"] = DELIVERY_WINDOW_PRESET
# Páginas HTTP Messages.json por conta (útil para ver truncagem em activity).
new_state["api_pages_by_account"] = {
    r["nome"]: r.get("api_pages", 0) for r in resultados_raw if r is not None
}
new_state["api_pages_capped_by_account"] = {
    r["nome"]: True for r in resultados_raw if r is not None and r.get("api_pages_capped")
}
if FETCH_MODE == "baseline_mes":
    if alguma_api_ok:
        new_state["baseline_month"] = cur_month
        new_state["baseline_completed_at"] = new_state["last_run_utc"]
    else:
        print("⚠️ Baseline mensal: nenhuma conta obteve HTTP 200 — baseline_month não atualizado (auto repetirá o baseline).")
elif FETCH_MODE == "baseline_24h":
    new_state["last_baseline_24h_at"] = new_state["last_run_utc"]
save_state(new_state)
print(f"💾 {STATE_PATH} atualizado (baseline_month={new_state.get('baseline_month')})")

print(f"✨ Concluído em {EXTRAIDO_EM}")
