import requests
import csv
import os
import concurrent.futures
from datetime import datetime
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

load_dotenv()

csv_saldos = "conf_saldos.csv"

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

def buscar_saldo(acc):
    sid, token, nome, cat = acc["sid"], acc["token"], acc["nome"], acc["categoria"]
    if not sid or not token:
        print(f"⚠️  Pulei {nome}: credenciais ausentes.")
        return None

    try:
        url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Balance.json"
        r = requests.get(url, auth=HTTPBasicAuth(sid, token), timeout=15)

        if r.status_code == 200:
            data = r.json()
            saldo = float(data.get("balance", 0))
            moeda = data.get("currency", "USD")
            print(f"✅ {nome} [{cat}] — Saldo: {moeda} {saldo:.2f}")
            return {
                "nome": nome,
                "categoria": cat,
                "saldo": round(saldo, 2),
                "moeda": moeda,
                "atualizado_em": datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
            }
        else:
            print(f"❌ Erro {r.status_code} em {nome}: {r.text}")
            return None

    except Exception as e:
        print(f"❌ Falha em {nome}: {e}")
        return None

# --- Execução Paralela ---
print(f"💰 Buscando saldos de {len(accounts)} contas...\n")

with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
    resultados = list(executor.map(buscar_saldo, accounts))

resultados = [r for r in resultados if r is not None]

# Sempre sobrescreve — saldo é snapshot atual, não histórico
with open(csv_saldos, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["Conta", "Categoria", "Saldo_USD", "Moeda", "Atualizado_Em"])
    for r in resultados:
        w.writerow([r["nome"], r["categoria"], r["saldo"], r["moeda"], r["atualizado_em"]])

saldo_total = sum(r["saldo"] for r in resultados)
print(f"\n💵 Saldo Total de todas as contas: ${saldo_total:,.2f}")
print(f"📄 {csv_saldos} atualizado com {len(resultados)} conta(s)")
