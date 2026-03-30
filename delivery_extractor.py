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
    """Converte data da Twilio para slot de 15min."""
    if not dt_str: return None
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(dt_str)
        minuto_slot = (dt.minute // 15) * 15
        return dt.strftime(f'%Y-%m-%d %H:{minuto_slot:02d}')
    except:
        return None

def processar_conta(acc):
    sid, token, nome, cat = acc["sid"], acc["token"], acc["nome"], acc["categoria"]
    if not sid or not token: return None

    session = requests.Session()
    session.auth = HTTPBasicAuth(sid, token)

    # ADICIONADO: Sent e Sending na estrutura de dados
    stats = {"Total": 0, "Delivered": 0, "Failed": 0, "Undelivered": 0, "Sent": 0, "Sending": 0, "Unknown": 0}
    horario = {}

    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    params = {"DateSent>": FILTRO_INICIO, "PageSize": 1000}

    while url:
        try:
            r = session.get(url, params=params, timeout=30)
            if r.status_code != 200: break
            body = r.json()
            msgs = body.get("messages", [])
            for m in msgs:
                status = m.get("status", "unknown").lower()
                sent_at = m.get("date_sent") or m.get("date_created", "")
                slot = slot_15min(sent_at)
                
                stats["Total"] += 1
                
                # Mapeamento expandido de status
                if status == "delivered":
                    stats["Delivered"] += 1; chave = "Delivered"
                elif status == "failed":
                    stats["Failed"] += 1; chave = "Failed"
                elif status in ["undelivered", "rejected"]:
                    stats["Undelivered"] += 1; chave = "Undelivered"
                elif status == "sent":
                    stats["Sent"] += 1; chave = "Sent"
                elif status in ["sending", "queued"]:
                    stats["Sending"] += 1; chave = "Sending"
                else:
                    stats["Unknown"] += 1; chave = "Unknown"

                if slot:
                    if slot not in horario:
                        horario[slot] = {"Delivered": 0, "Failed": 0, "Undelivered": 0, "Sent": 0, "Sending": 0, "Unknown": 0}
                    horario[slot][chave] += 1

            next_uri = body.get("next_page_uri")
            url = f"https://api.twilio.com{next_uri}" if next_uri else None
            params = {}
        except:
            break

    taxa = round((stats["Delivered"] / stats["Total"] * 100), 2) if stats["Total"] > 0 else 0.0
    return {"nome": nome, "cat": cat, "stats": stats, "taxa": taxa, "horario": horario}

with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
    resultados = [r for r in executor.map(processar_conta, accounts) if r and r["stats"]["Total"] > 0]

EXTRAIDO_EM = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')

# --- Salva Stats (Snapshot) ---
header_stats = ["Conta", "Categoria", "Janela", "Total", "Delivered", "Failed", "Undelivered", "Sent", "Sending", "Unknown", "Taxa_Entrega_%", "Extraido_Em"]
rows_stats = [[
    r["nome"], r["cat"], JANELA_LABEL, r["stats"]["Total"],
    r["stats"]["Delivered"], r["stats"]["Failed"], r["stats"]["Undelivered"],
    r["stats"]["Sent"], r["stats"]["Sending"], r["stats"]["Unknown"],
    r["taxa"], EXTRAIDO_EM
] for r in resultados]

with open(csv_stats, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(header_stats)
    w.writerows(rows_stats)

# --- Salva Horário (Acumulado) ---
header_horario = ["Slot_15min", "Conta", "Categoria", "Delivered", "Failed", "Undelivered", "Sent", "Sending", "Unknown", "Total_Slot"]
# Lógica de dedup simplificada para o exemplo
with open(csv_horario, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(header_horario)
    for r in resultados:
        for slot, b in r["horario"].items():
            w.writerow([slot, r["nome"], r["cat"], b["Delivered"], b["Failed"], b["Undelivered"], b["Sent"], b["Sending"], b["Unknown"], sum(b.values())])

print(f"✨ Concluído em {EXTRAIDO_EM}. Arquivos atualizados com colunas Sent/Sending.")