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
STATE_PATH = os.getenv("DELIVERY_STATE_FILE", "delivery_sync_state.json")
# outbound = só saída (Messaging Insights com Outgoing). all = todas as direções (legado).
DELIVERY_DIRECTION = os.getenv("DELIVERY_DIRECTION", "outbound").strip().lower()
if DELIVERY_DIRECTION not in ("outbound", "all"):
    DELIVERY_DIRECTION = "outbound"

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
JANELA_HORAS = float(os.getenv("DELIVERY_JANELA_HORAS", "0.25"))
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

if FETCH_MODE == "incremental":
    since_dt = AGORA - timedelta(hours=JANELA_HORAS)
    JANELA_LABEL = f"{int(JANELA_HORAS * 60)}min" if JANELA_HORAS < 1 else f"{int(JANELA_HORAS)}h"
elif FETCH_MODE == "baseline_mes":
    since_dt = inicio_mes_utc(AGORA)
    JANELA_LABEL = f"baseline_mes_{cur_month}"
else:  # baseline_24h
    since_dt = AGORA - timedelta(hours=24)
    JANELA_LABEL = "baseline_24h"

FILTRO_INICIO = since_dt.strftime("%Y-%m-%dT%H:%M:%SZ")


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
    params = {"DateSent>": FILTRO_INICIO, "PageSize": 1000}
    pagina = 0

    while url:
        try:
            r = session.get(url, params=params, timeout=60)
            if r.status_code != 200:
                print(f"⚠️ {nome}: HTTP {r.status_code}")
                break
            api_ok = True
            body = r.json()
            pagina += 1
            if pagina % 50 == 0:
                print(f"… {nome}: página {pagina}")

            for m in body.get("messages", []):
                if not mensagem_conta_para_extracao(m):
                    continue
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

            next_uri = body.get("next_page_uri")
            url = f"https://api.twilio.com{next_uri}" if next_uri else None
            params = {}
        except Exception as e:
            print(f"❌ Falha em {nome}: {e}")
            break

    taxa = round((stats_seg["Delivered"] / stats_seg["Total"] * 100), 2) if stats_seg["Total"] > 0 else 0.0
    print(f"✅ {nome} [{cat}] — {stats_msg['Total']} msgs | {stats_seg['Total']} segmentos | {taxa}% entregues")
    return {
        "nome": nome,
        "cat": cat,
        "stats_msg": stats_msg,
        "stats_seg": stats_seg,
        "taxa": taxa,
        "horario": horario,
        "api_ok": api_ok,
    }


migrar_horario_se_schema_antigo()

print(
    f"🚀 Delivery | modo={FETCH_MODE} | direção={DELIVERY_DIRECTION} | janela_label={JANELA_LABEL} | "
    f"DateSent>={FILTRO_INICIO} UTC | agora={AGORA.strftime('%Y-%m-%dT%H:%M:%SZ')} | {len(accounts)} contas"
)

with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
    resultados_raw = list(executor.map(processar_conta, accounts))
resultados_raw = [r for r in resultados_raw if r is not None]
# CSV snapshot: só contas com volume; estado baseline exige pelo menos uma conta com API OK
resultados = [r for r in resultados_raw if r["stats_seg"]["Total"] > 0]
alguma_api_ok = any(r.get("api_ok") for r in resultados_raw)

EXTRAIDO_EM = AGORA.strftime("%Y-%m-%d %H:%M UTC")

# --- conf_delivery_stats.csv ---
header_stats = (
    ["Conta", "Categoria", "Janela", "Modo", "Direcao", "Mensagens", "Segmentos"]
    + CATEGORIAS
    + ["Taxa_Entrega_%", "Extraido_Em"]
)
with open(csv_stats, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(header_stats)
    for r in resultados:
        row = [
            r["nome"],
            r["cat"],
            JANELA_LABEL,
            FETCH_MODE,
            DELIVERY_DIRECTION,
            r["stats_msg"]["Total"],
            r["stats_seg"]["Total"],
        ]
        for c in CATEGORIAS:
            row.append(r["stats_seg"][c])
        row.extend([r["taxa"], EXTRAIDO_EM])
        w.writerow(row)
print(f"📄 {csv_stats} — {len(resultados)} conta(s), segmentos por categoria (dash)")

# --- conf_delivery_horario.csv (append) ---
chaves_horario = carregar_chaves_existentes(csv_horario, key_cols=[0, 1])
novas_horario = []
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

# --- Estado (auto: baseline mensal uma vez por mês; depois incremental rápido) ---
new_state = dict(state)
new_state["last_run_utc"] = AGORA.strftime("%Y-%m-%dT%H:%M:%SZ")
new_state["last_fetch_mode"] = FETCH_MODE
new_state["delivery_direction"] = DELIVERY_DIRECTION
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
