import requests
import csv
import os
import concurrent.futures
from datetime import datetime
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

load_dotenv()

accounts = [
    {"sid": os.getenv("RECUPERACAO_NS_SID"), "token": os.getenv("RECUPERACAO_NS_TOKEN"), "nome": "NS", "categoria": "Recuperação"},
    {"sid": os.getenv("BROADCAST_JOAO_SID"), "token": os.getenv("BROADCAST_JOAO_TOKEN"), "nome": "Joao", "categoria": "Broadcast"},
    {"sid": os.getenv("BROADCAST_BERNARDO_SID"), "token": os.getenv("BROADCAST_BERNARDO_TOKEN"), "nome": "Bernardo", "categoria": "Broadcast"},
    {"sid": os.getenv("BROADCAST_RAFA_SID"), "token": os.getenv("BROADCAST_RAFA_TOKEN"), "nome": "Rafa", "categoria": "Broadcast"},
    {"sid": os.getenv("STANDBY_HAVEN_SID"), "token": os.getenv("STANDBY_HAVEN_TOKEN"), "nome": "Havenmove", "categoria": "Standby"},
    {"sid": os.getenv("STANDBY_REHABLEAF_SID"), "token": os.getenv("STANDBY_REHABLEAF_TOKEN"), "nome": "Rehableaf", "categoria": "Standby"},
    {"sid": os.getenv("STANDBY_RICHARD_SID"), "token": os.getenv("STANDBY_RICHARD_TOKEN"), "nome": "Richard", "categoria": "Standby"},
    {"sid": os.getenv("STANDBY_NATUREMOVE_SID"), "token": os.getenv("STANDBY_NATUREMOVE_TOKEN"), "nome": "Naturemove", "categoria": "Standby"}
]

today = datetime.today()
START_DATE = today.strftime('%Y-%m-01')  # início do mês
END_DATE   = today.strftime('%Y-%m-%d')  # hoje

csv_total     = "conf_total_marco.csv"
csv_detalhado = "conf_detalhado_marco.csv"

MAPEAMENTO_GRUPOS = {
    "SMS: Envio/Recebimento":   ["sms-outbound-longcode", "sms-inbound-longcode", "sms-outbound-shortcode"],
    "SMS: Taxas de Operadora":  ["sms-messages-carrier-fees", "usage-rcs-messaging-carrier-fees"],
    "Voz: Chamadas e Minutos":  ["calls-inbound", "calls-outbound", "calls-emergency"],
    "Voz: Gravações e Storage": ["calls-recordings", "recordings"],
    "IA: Transcrição e Speech": ["voice-intelligence-transcription", "amazon-polly", "marketplace-google-speech-to-text"],
    "Segurança: Lookups e Verify": ["lookup-identity-match", "lookups", "verify-push-attempts"],
    "Assinaturas: Números Fixos":  ["phonenumbers-local", "phonenumbers-mobile"]
}

def processar_conta(acc):
    sid, token, nome, cat = acc["sid"], acc["token"], acc["nome"], acc["categoria"]
    if not sid or not token:
        print(f"⚠️ Pulei {nome}: credenciais ausentes.")
        return None

    session = requests.Session()
    session.auth = HTTPBasicAuth(sid, token)

    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Usage/Records/Daily.json"
    params = {"StartDate": START_DATE, "EndDate": END_DATE, "PageSize": 1000}

    resumo_dia  = {}
    detalhe_dia = {}

    while url:
        try:
            response = session.get(url, params=params, timeout=30)
            if response.status_code == 200:
                body = response.json()
                for r in body.get("usage_records", []):
                    data_ref    = r['start_date']
                    cat_twilio  = r['category']
                    preco_bruto = float(r['price'])
                    uso         = int(float(r['usage']))

                    if cat_twilio == 'totalprice':
                        preco_final = preco_bruto / 100000 if preco_bruto > 100000 else preco_bruto
                    else:
                        preco_final = preco_bruto / 100000 if preco_bruto > 1.0 else preco_bruto

                    if data_ref not in resumo_dia:
                        resumo_dia[data_ref] = {"gasto": 0.0, "volume": 0}
                    if cat_twilio == 'totalprice':
                        resumo_dia[data_ref]["gasto"] = round(preco_final, 2)
                    elif cat_twilio == 'sms':
                        resumo_dia[data_ref]["volume"] = uso

                    if data_ref not in detalhe_dia:
                        detalhe_dia[data_ref] = {g: 0.0 for g in MAPEAMENTO_GRUPOS}
                    for grupo, lista_cats in MAPEAMENTO_GRUPOS.items():
                        if cat_twilio in lista_cats:
                            detalhe_dia[data_ref][grupo] += preco_final

                next_uri = body.get("next_page_uri")
                url = f"https://api.twilio.com{next_uri}" if next_uri else None
                params = {}
            else:
                print(f"❌ Erro {response.status_code} em {nome}")
                url = None
        except Exception as e:
            print(f"❌ Falha em {nome}: {e}")
            url = None

    print(f"✅ {nome} [{cat}] — {len(resumo_dia)} dia(s)")
    return {"nome": nome, "cat": cat, "resumo_dia": resumo_dia, "detalhe_dia": detalhe_dia}

print(f"🚀 Extrator Financeiro | {START_DATE} → {END_DATE} | {len(accounts)} contas em paralelo")

with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
    resultados = list(executor.map(processar_conta, accounts))
resultados = [r for r in resultados if r is not None]

# Sempre sobrescreve com o mês completo e atualizado
data_total     = []
data_detalhado = []

for r in resultados:
    for d, v in r["resumo_dia"].items():
        if v["gasto"] > 0 or v["volume"] > 0:
            data_total.append([r["nome"], r["cat"], d, f"{v['gasto']:.2f}", v["volume"]])
    for d, grupos in r["detalhe_dia"].items():
        for g_nome, g_valor in grupos.items():
            if g_valor > 0:
                data_detalhado.append([d, r["nome"], r["cat"], g_nome, round(g_valor, 4)])

data_total.sort(key=lambda x: x[2], reverse=True)
data_detalhado.sort(key=lambda x: (x[0], x[1]), reverse=True)

with open(csv_total, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["Conta", "Categoria", "Data", "Gasto USD", "SMS_Transactions"])
    w.writerows(data_total)

with open(csv_detalhado, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["Data", "Conta", "Categoria", "Grupo_Gasto", "Valor_USD"])
    w.writerows(data_detalhado)

print(f"✨ CSVs financeiros atualizados: {len(data_total)} linhas total | {len(data_detalhado)} linhas detalhado")
