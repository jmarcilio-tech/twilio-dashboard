import requests
import csv
import os
import concurrent.futures
from datetime import datetime, timedelta
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

load_dotenv()

# --- Configuração do Período ---
# Altere JANELA_HORAS para mudar o período de análise:
# 0.25 = 15 minutos | 1 = 1 hora | 4 = 4 horas | 24 = 1 dia | 168 = 7 dias
JANELA_HORAS = float(os.getenv("DELIVERY_JANELA_HORAS", "0.25"))
FILTRO_INICIO = (datetime.utcnow() - timedelta(hours=JANELA_HORAS)).strftime('%Y-%m-%dT%H:%M:%SZ')
AGORA = datetime.utcnow()

csv_stats    = "conf_delivery_stats.csv"
csv_horario  = "conf_delivery_horario.csv"

accounts = [
    {"sid": os.getenv("RECUPERACAO_NS_SID"),       "token": os.getenv("RECUPERACAO_NS_TOKEN"),       "nome": "NS",          "categoria": "Recuperação"},
    {"sid": os.getenv("BROADCAST_JOAO_SID"),        "token": os.getenv("BROADCAST_JOAO_TOKEN"),        "nome": "Joao",        "categoria": "Broadcast"},
    {"sid": os.getenv("BROADCAST_BERNARDO_SID"),    "token": os.getenv("BROADCAST_BERNARDO_TOKEN"),    "nome": "Bernardo",    "categoria": "Broadcast"},
    {"sid": os.getenv("BROADCAST_RAFA_SID"),        "token": os.getenv("BROADCAST_RAFA_TOKEN"),        "nome": "Rafa",        "categoria": "Broadcast"},
    {"sid": os.getenv("STANDBY_HAVEN_SID"),         "token": os.getenv("STANDBY_HAVEN_TOKEN"),         "nome": "Havenmove",   "categoria": "Standby"},
    {"sid": os.getenv("STANDBY_REHABLEAF_SID"),     "token": os.getenv("STANDBY_REHABLEAF_TOKEN"),     "nome": "Rehableaf",   "categoria": "Standby"},
    {"sid": os.getenv("STANDBY_RICHARD_SID"),       "token": os.getenv("STANDBY_RICHARD_TOKEN"),       "nome": "Richard",     "categoria": "Standby"},
    {"sid": os.getenv("STANDBY_NATUREMOVE_SID"),    "token": os.getenv("STANDBY_NATUREMOVE_TOKEN"),    "nome": "Naturemove",  "categoria": "Standby"},
]

def slot_15min(dt_str):
    """Converte uma data ISO para slot de 15min. Ex: '17:00', '17:15', '17:30', '17:45'"""
    try:
        dt = datetime.strptime(dt_str[:19], '%Y-%m-%dT%H:%M:%S')
        minuto_slot = (dt.minute // 15) * 15
        return dt.strftime(f'%Y-%m-%d %H:{minuto_slot:02d}')
    except:
        return "desconhecido"

def processar_conta(acc):
    sid, token, nome, cat = acc["sid"], acc["token"], acc["nome"], acc["categoria"]
    if not sid or not token:
        print(f"⚠️  Pulei {nome}: credenciais ausentes.")
        return None

    session = requests.Session()
    session.auth = HTTPBasicAuth(sid, token)

    stats = {"Total": 0, "Delivered": 0, "Failed": 0, "Undelivered": 0, "Unknown": 0}
    horario = {}  # { "2026-03-29 17:00": {"Delivered": 0, "Failed": 0, ...} }

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

                # Acumula stats globais
                stats["Total"] += 1
                if status == "delivered":
                    stats["Delivered"] += 1
                    chave = "Delivered"
                elif status == "failed":
                    stats["Failed"] += 1
                    chave = "Failed"
                elif status == "undelivered":
                    stats["Undelivered"] += 1
                    chave = "Undelivered"
                else:
                    stats["Unknown"] += 1
                    chave = "Unknown"

                # Acumula breakdown por slot de 15min
                if slot not in horario:
                    horario[slot] = {"Delivered": 0, "Failed": 0, "Undelivered": 0, "Unknown": 0}
                horario[slot][chave] += 1

            next_uri = body.get("next_page_uri")
            url = f"https://api.twilio.com{next_uri}" if next_uri else None
            params = {}

        except Exception as e:
            print(f"❌ Falha em {nome}: {e}")
            break

    taxa_entrega = round((stats["Delivered"] / stats["Total"] * 100), 2) if stats["Total"] > 0 else 0.0
    print(f"✅ {nome} [{cat}] — {stats['Total']} msgs | {taxa_entrega}% entregues | {paginas} pág(s)")

    return {
        "nome": nome,
        "cat": cat,
        "stats": stats,
        "taxa_entrega": taxa_entrega,
        "horario": horario
    }

# --- Execução Paralela ---
janela_label = f"{int(JANELA_HORAS * 60)}min" if JANELA_HORAS < 1 else f"{int(JANELA_HORAS)}h"
print(f"🚀 Extração Delivery & Errors | Janela: últimos {janela_label} | Início: {FILTRO_INICIO} UTC")
print(f"🔀 Processando {len(accounts)} contas em paralelo...\n")

with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
    resultados = list(executor.map(processar_conta, accounts))

resultados = [r for r in resultados if r is not None]

# --- Salvar conf_delivery_stats.csv ---
with open(csv_stats, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["Conta", "Categoria", "Janela", "Total", "Delivered", "Failed", "Undelivered", "Unknown", "Taxa_Entrega_%", "Extraido_Em"])
    for r in sorted(resultados, key=lambda x: x["stats"]["Total"], reverse=True):
        w.writerow([
            r["nome"],
            r["cat"],
            janela_label,
            r["stats"]["Total"],
            r["stats"]["Delivered"],
            r["stats"]["Failed"],
            r["stats"]["Undelivered"],
            r["stats"]["Unknown"],
            r["taxa_entrega"],
            AGORA.strftime('%Y-%m-%d %H:%M UTC')
        ])

# --- Salvar conf_delivery_horario.csv ---
with open(csv_horario, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["Slot_15min", "Conta", "Categoria", "Delivered", "Failed", "Undelivered", "Unknown", "Total_Slot"])
    linhas = []
    for r in resultados:
        for slot, breakdown in r["horario"].items():
            total_slot = sum(breakdown.values())
            linhas.append([
                slot,
                r["nome"],
                r["cat"],
                breakdown["Delivered"],
                breakdown["Failed"],
                breakdown["Undelivered"],
                breakdown["Unknown"],
                total_slot
            ])
    linhas.sort(key=lambda x: (x[0], x[1]), reverse=True)
    w.writerows(linhas)

print(f"\n✨ CSVs salvos:")
print(f"   📄 {csv_stats}   — resumo por conta")
print(f"   📄 {csv_horario} — breakdown por slot de 15min")
