import requests
import csv
import os
import concurrent.futures
from datetime import datetime, timedelta
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

load_dotenv()

# --- Configuração da Janela ---
JANELA_HORAS = float(os.getenv("DELIVERY_JANELA_HORAS", "0.25"))
AGORA = datetime.utcnow()
FILTRO_INICIO = (AGORA - timedelta(hours=JANELA_HORAS)).strftime('%Y-%m-%dT%H:%M:%SZ')
JANELA_LABEL = f"{int(JANELA_HORAS * 60)}min" if JANELA_HORAS < 1 else f"{int(JANELA_HORAS)}h"

csv_stats   = "conf_delivery_stats.csv"
csv_horario = "conf_delivery_horario.csv"

accounts = [
    {"sid": os.getenv("RECUPERACAO_NS_SID"),       "token": os.getenv("RECUPERACAO_NS_TOKEN"),       "nome": "NS",         "categoria": "Recuperação"},
    {"sid": os.getenv("BROADCAST_JOAO_SID"),        "token": os.getenv("BROADCAST_JOAO_TOKEN"),        "nome": "Joao",       "categoria": "Broadcast"},
    {"sid": os.getenv("BROADCAST_BERNARDO_SID"),    "token": os.getenv("BROADCAST_BERNARDO_TOKEN"),    "nome": "Bernardo",   "categoria": "Broadcast"},
    {"sid": os.getenv("BROADCAST_RAFA_SID"),        "token": os.getenv("BROADCAST_RAFA_TOKEN"),        "nome": "Rafa",       "categoria": "Broadcast"},
    {"sid": os.getenv("STANDBY_HAVEN_SID"),         "token": os.getenv("STANDBY_HAVEN_TOKEN"),         "nome": "Havenmove",  "categoria": "Standby"},
    {"sid": os.getenv("STANDBY_REHABLEAF_SID"),     "token": os.getenv("STANDBY_REHABLEAF_TOKEN"),     "nome": "Rehableaf",  "categoria": "Standby"},
    {"sid": os.getenv("STANDBY_RICHARD_SID"),       "token": os.getenv("STANDBY_RICHARD_TOKEN"),       "nome": "Richard",    "categoria": "Standby"},
    {"sid": os.getenv("STANDBY_NATUREMOVE_SID"),    "token": os.getenv("STANDBY_NATUREMOVE_TOKEN"),    "nome": "Naturemove", "categoria": "Standby"},
]

_debug_printed = False

def slot_15min(dt_str):
    """Converte data da Twilio para slot de 15min. Suporta múltiplos formatos."""
    global _debug_printed
    if not dt_str:
        return None

    # Debug: mostra o formato real na primeira mensagem
    if not _debug_printed:
        print(f"🔍 DEBUG formato de data Twilio: '{dt_str}'")
        _debug_printed = True

    # Formato RFC 2822 que a Twilio usa: "Sun, 29 Mar 2026 23:03:00 +0000"
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(dt_str)
        minuto_slot = (dt.minute // 15) * 15
        return dt.strftime(f'%Y-%m-%d %H:{minuto_slot:02d}')
    except:
        pass

    # Fallbacks
    formatos = [
        '%Y-%m-%dT%H:%M:%SZ',
        '%Y-%m-%dT%H:%M:%S',
        '%a, %d %b %Y %H:%M:%S %z',
        '%a, %d %b %Y %H:%M:%S GMT',
    ]
    for fmt in formatos:
        try:
            dt = datetime.strptime(dt_str.strip(), fmt)
            minuto_slot = (dt.minute // 15) * 15
            return dt.strftime(f'%Y-%m-%d %H:{minuto_slot:02d}')
        except:
            continue
    try:
        dt = datetime.strptime(dt_str[:16], '%Y-%m-%dT%H:%M')
        minuto_slot = (dt.minute // 15) * 15
        return dt.strftime(f'%Y-%m-%d %H:{minuto_slot:02d}')
    except:
        print(f"⚠️  Não conseguiu parsear: '{dt_str}'")
        return None

def carregar_chaves_existentes(filepath, key_cols):
    chaves = set()
    if not os.path.exists(filepath):
        return chaves
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if row:
                chaves.add(tuple(row[i] for i in key_cols))
    return chaves

def processar_conta(acc):
    sid, token, nome, cat = acc["sid"], acc["token"], acc["nome"], acc["categoria"]
    if not sid or not token:
        print(f"⚠️  Pulei {nome}: credenciais ausentes.")
        return None

    session = requests.Session()
    session.auth = HTTPBasicAuth(sid, token)

    stats = {"Total": 0, "Delivered": 0, "Failed": 0, "Undelivered": 0, "Unknown": 0}
    horario = {}

    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    params = {"DateSent>": FILTRO_INICIO, "PageSize": 1000}
    paginas = 0

    while url:
        try:
            r = session.get(url, params=params, timeout=30)
            if r.status_code != 200:
                print(f"❌ Erro {r.status_code} em {nome}")
                break
            body = r.json()
            msgs = body.get("messages", [])
            paginas += 1
            for m in msgs:
                status = m.get("status", "unknown")
                sent_at = m.get("date_sent") or m.get("date_created", "")
                slot = slot_15min(sent_at)
                stats["Total"] += 1
                if status == "delivered":
                    stats["Delivered"] += 1; chave = "Delivered"
                elif status == "failed":
                    stats["Failed"] += 1; chave = "Failed"
                elif status == "undelivered":
                    stats["Undelivered"] += 1; chave = "Undelivered"
                else:
                    stats["Unknown"] += 1; chave = "Unknown"
                if slot and slot not in horario:
                    horario[slot] = {"Delivered": 0, "Failed": 0, "Undelivered": 0, "Unknown": 0}
                if slot: horario[slot][chave] += 1
            next_uri = body.get("next_page_uri")
            url = f"https://api.twilio.com{next_uri}" if next_uri else None
            params = {}
        except Exception as e:
            print(f"❌ Falha em {nome}: {e}")
            break

    taxa = round((stats["Delivered"] / stats["Total"] * 100), 2) if stats["Total"] > 0 else 0.0
    print(f"✅ {nome} [{cat}] — {stats['Total']} msgs | {taxa}% entregues | {paginas} pág(s)")
    return {"nome": nome, "cat": cat, "stats": stats, "taxa": taxa, "horario": horario}

# --- Execução Paralela ---
print(f"🚀 Extração Delivery | Janela: últimos {JANELA_LABEL} | De: {FILTRO_INICIO} UTC")
print(f"🔀 Processando {len(accounts)} contas em paralelo...\n")

with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
    resultados = list(executor.map(processar_conta, accounts))

resultados = [r for r in resultados if r is not None and r["stats"]["Total"] > 0]
EXTRAIDO_EM = AGORA.strftime('%Y-%m-%d %H:%M UTC')

# --- Sobrescrever conf_delivery_stats.csv (snapshot atual) ---
# Sempre recria do zero com a foto mais recente de cada conta
rows_stats = []
for r in resultados:
    rows_stats.append([
        r["nome"], r["cat"], JANELA_LABEL,
        r["stats"]["Total"], r["stats"]["Delivered"],
        r["stats"]["Failed"], r["stats"]["Undelivered"],
        r["stats"]["Unknown"], r["taxa"], EXTRAIDO_EM
    ])

with open(csv_stats, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["Conta", "Categoria", "Janela", "Total", "Delivered", "Failed", "Undelivered", "Unknown", "Taxa_Entrega_%", "Extraido_Em"])
    w.writerows(rows_stats)
print(f"📄 {csv_stats} — sobrescrito com {len(rows_stats)} conta(s) | snapshot de {EXTRAIDO_EM}")

# --- Acumular conf_delivery_horario.csv ---
# Chave: Slot_15min + Conta (evita duplicar o mesmo slot)
chaves_horario = carregar_chaves_existentes(csv_horario, key_cols=[0, 1])
novas_horario = []
for r in resultados:
    for slot, breakdown in r["horario"].items():
        if (slot, r["nome"]) not in chaves_horario:
            novas_horario.append([
                slot, r["nome"], r["cat"],
                breakdown["Delivered"], breakdown["Failed"],
                breakdown["Undelivered"], breakdown["Unknown"],
                sum(breakdown.values())
            ])

escrever_header = not os.path.exists(csv_horario)
with open(csv_horario, "a", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    if escrever_header:
        w.writerow(["Slot_15min", "Conta", "Categoria", "Delivered", "Failed", "Undelivered", "Unknown", "Total_Slot"])
    w.writerows(novas_horario)
print(f"📄 {csv_horario} — {len(novas_horario)} linha(s) novas adicionadas")
print(f"\n✨ Acumulação concluída em {EXTRAIDO_EM}")
