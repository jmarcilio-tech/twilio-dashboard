# 📊 Twilio Financial Intelligence - Data Pipeline

Este repositório contém o pipeline automatizado de extração, tratamento e consolidação de dados financeiros provenientes da API v2010 da Twilio. O sistema centraliza o consumo de 8 subcontas distintas, permitindo a análise granular de custos operacionais, taxas de operadora e volumetria de tráfego para alimentação de dashboards de Business Intelligence (Lovable/Streamlit).

## 🛠️ Stack Tecnológica

* **Linguagem:** Python 3.10+
* **Orquestração:** GitHub Actions
* **Protocolo de API:** REST / HTTP Basic Auth
* **Formatos de Saída:** CSV (Datasets normalizados)

## 🏗️ Arquitetura e Performance

O motor de extração foi desenvolvido seguindo boas práticas de engenharia de dados para garantir escalabilidade e baixo consumo de recursos:

* **Connection Pooling:** Utiliza `requests.Session()` para reaproveitamento de conexões TCP/SSL, reduzindo o overhead de handshake em ~20%.
* **Tratamento de Escala:** Lógica integrada para normalização de precisão decimal, corrigindo flutuações nativas da API Twilio em registros de alta granularidade.
* **Paginação Automática:** Gestão dinâmica de buffers via `next_page_uri` para suportar grandes volumes de dados sem estouro de memória.

## 🔐 Segurança e Compliance

O projeto adere aos princípios do *12-Factor App* para gestão de configurações:

* **Zero-Config no Código:** Nenhuma credencial é armazenada no repositório.
* **Injeção de Runtime:** As credenciais (Account SIDs e Auth Tokens) são injetadas em tempo de execução via **GitHub Repository Secrets**.
* **Escopo de Permissões:** O workflow de CI/CD utiliza permissões granulares de escrita (`contents: write`) restritas aos datasets gerados.

## 🚀 Pipeline de CI/CD

A atualização dos dados é orquestrada via GitHub Actions com a seguinte política:

* **Frequência:** Execução recorrente a cada 15 minutos (`cron: '*/15 * * * *'`).
* **Persistence Layer:** O robô realiza o commit automático dos arquivos `conf_total_marco.csv` e `conf_detalhado_marco.csv` de volta ao repositório.
* **Data Integrity:** Inclui etapa de ordenação (sort) pós-processamento para garantir que consumidores de dados (Dashboards) acessem sempre os registros cronológicos mais recentes.

## 📊 Estrutura dos Datasets

| Arquivo | Nível de Granularidade | Principais Métricas |
| :--- | :--- | :--- |
| `conf_total_marco.csv` | Executivo / Diário | Gasto Total USD, Volume de SMS. |
| `conf_detalhado_marco.csv` | Operacional / Categoria | Custos de Voz, IA, Lookups e Assinaturas. |
| `conf_delivery_stats.csv` | Messaging / snapshot (~5 min) | Uma linha por conta: segmentos por estado, `List_Mode`, `Api_Pages*`, Insights por mensagem (`delivery-only.yml`). |
| `conf_delivery_insights_4h.csv` | Messaging / Insights consola | Past N h (default 4), `activity` + outbound; colunas `Insight_*` + `*_Seg` (`delivery-insights-4h.yml`). |
| `conf_delivery_horario.csv` | Messaging / série 15 min UTC | Slots agregados; não substitui o snapshot para o mesmo “total” da consola. |
| `conf_delivery_stats_history.csv` | Messaging / append diário | Mesmo schema que stats; série longa (`delivery-sweep-daily.yml`). |
| `conf_usage_billing_snapshot.csv` | Billing / Usage API | Default **`cover_days`** (soma dias UTC da janela ~24h; alinha melhor a **SMS Transactions** do Account Insights). Legado: `rolling_24h_proxy` (blend horário). Colunas `TotalPrice_Totalprice`, `SMS_Price`, `SMS_Count`, `SMS_Usage`; ver `Range`. |
| `conf_usage_billing_by_category.csv` | Billing / Usage API | Uma linha por `(Conta, Categoria)` com `Count`, `Usage`, `Price_USD` (todas as categorias Twilio na mesma janela; ver `docs/lovable-usage-hybrid/`). |
| `conf_usage_billing_daily.csv` | Billing / Usage API | Série **diária** GMT (`Usage/Records/Daily`): `Conta`, `Data_Utc`, `Categoria`, `Count`, `Usage`, `Price_USD`, `Range`, `Extraido_Utc` — default categorias `totalprice` + `sms` (env `USAGE_DAILY_CATEGORIES`). |
| `month/conf_usage_billing_*.csv` | Billing / Usage API | **Mesmo trio** de ficheiros quando o run usa `USAGE_START_DATE`+`USAGE_END_DATE` (ex. workflow `billing_month`). Não substitui os CSVs **rolling** na raiz; o toggle “Mês” na UI deve ler `month/`. |

Instruções para consumidores (Lovable / BI): **layout em 3 abas isoladas** em **`docs/lovable-dashboard-3-abas.md`**; referência técnica completa e prompt longo em **`docs/pipeline-documentacao.md`** (secções 10 e 10.1). **Nomes e ordem das subcontas** (coluna `Conta` nos CSVs): `data/accounts_canonical.json` no repo — alinhar dropdowns na Lovable; o pipeline usa **`accounts_catalog.py`** como fonte única em Python.

## 🛠️ Manutenção e Expansão

Para adicionar uma nova subconta ao monitoramento:

1.  Insira as configurações de `sid`, `token`, `nome` e `categoria` no dicionário `accounts` dentro do script principal.
2.  Configure os respectivos **Secrets** na interface do GitHub (`Settings > Secrets and variables > Actions`).
3.  Mapeie as novas variáveis nos workflows que usam essa conta (ex.: `.github/workflows/main.yml`, `delivery-only.yml`, `saldo-only.yml`, `usage-billing-snapshot.yml`, conforme aplicável).

---
*Mantido pela equipe de Engenharia / Data Ops.*