import requests
import csv
import os
from datetime import datetime
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

from accounts_catalog import accounts_from_env

load_dotenv()

# 1. Contas (fonte única: accounts_catalog)
accounts = accounts_from_env()

# Datas dinâmicas: sempre extrai do início do mês corrente até hoje
today = datetime.today()
START_DATE = today.strftime('%Y-%m-01')
END_DATE = today.strftime('%Y-%m-%d')

csv_total = "conf_total_marco.csv"
csv_detalhado = "conf_detalhado_marco.csv"

# Mapeamento de Grupos para a Aba 2
MAPEAMENTO_GRUPOS = {
    "SMS: Envio/Recebimento": ["sms-outbound-longcode", "sms-inbound-longcode", "sms-outbound-shortcode"],
    "SMS: Taxas de Operadora": ["sms-messages-carrier-fees", "usage-rcs-messaging-carrier-fees"],
    "Voz: Chamadas e Minutos": ["calls-inbound", "calls-outbound", "calls-emergency"],
    "Voz: Gravações e Storage": ["calls-recordings", "recordings"],
    "IA: Transcrição e Speech": ["voice-intelligence-transcription", "amazon-polly", "marketplace-google-speech-to-text"],
    "Segurança: Lookups e Verify": ["lookup-identity-match", "lookups", "verify-push-attempts"],
    "Assinaturas: Números Fixos": ["phonenumbers-local", "phonenumbers-mobile"]
}

data_total = []
data_detalhado = []

print(f"🚀 Iniciando extração unificada: {START_DATE} até {END_DATE}")

# Uso de Session para reutilizar conexões TCP (mais rápido no CI)
session = requests.Session()

for acc in accounts:
    sid, token, nome, cat = acc["sid"], acc["token"], acc["nome"], acc["categoria"]
    if not sid or not token:
        print(f"⚠️ Pulei {nome}: Credenciais faltando no .env.")
        continue

    print(f"📂 Processando: {nome} [{cat}]...")
    session.auth = HTTPBasicAuth(sid, token)

    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Usage/Records/Daily.json"
    params = {"StartDate": START_DATE, "EndDate": END_DATE, "PageSize": 1000}

    resumo_dia = {}
    detalhe_dia = {}

    while url:
        try:
            response = session.get(url, params=params)
            if response.status_code == 200:
                body = response.json()
                records = body.get("usage_records", [])
                for r in records:
                    data_ref = r['start_date']
                    cat_twilio = r['category']
                    preco_bruto = float(r['price'])
                    uso = int(float(r['usage']))

                    # Lógica de Correção de Preço
                    if cat_twilio == 'totalprice':
                        preco_final = preco_bruto / 100000 if preco_bruto > 100000 else preco_bruto
                    else:
                        preco_final = preco_bruto / 100000 if preco_bruto > 1.0 else preco_bruto

                    # Consolidado (Aba 1)
                    if data_ref not in resumo_dia:
                        resumo_dia[data_ref] = {"gasto": 0.0, "volume": 0}

                    if cat_twilio == 'totalprice':
                        resumo_dia[data_ref]["gasto"] = round(preco_final, 2)
                    elif cat_twilio == 'sms':
                        resumo_dia[data_ref]["volume"] = uso

                    # Detalhado (Aba 2)
                    if data_ref not in detalhe_dia:
                        detalhe_dia[data_ref] = {grupo: 0.0 for grupo in MAPEAMENTO_GRUPOS.keys()}

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

    for d, v in resumo_dia.items():
        if v["gasto"] > 0 or v["volume"] > 0:
            data_total.append([nome, cat, d, f"{v['gasto']:.2f}", v["volume"]])

    for d, grupos in detalhe_dia.items():
        for g_nome, g_valor in grupos.items():
            if g_valor > 0:
                data_detalhado.append([d, nome, cat, g_nome, round(g_valor, 4)])

# Salvando Arquivos
with open(csv_total, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["Conta", "Categoria", "Data", "Gasto USD", "SMS_Transactions"])
    data_total.sort(key=lambda x: x[2], reverse=True)
    w.writerows(data_total)

with open(csv_detalhado, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["Data", "Conta", "Categoria", "Grupo_Gasto", "Valor_USD"])
    data_detalhado.sort(key=lambda x: (x[0], x[1]), reverse=True)
    w.writerows(data_detalhado)

print(f"\n✨ Sucesso! CSVs atualizados: {csv_total} | {csv_detalhado}")
