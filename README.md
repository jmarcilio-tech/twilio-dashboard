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
* **Dependabot:** atualizações semanais de dependências Python (`.github/dependabot.yml`).
* **Política detalhada:** ver `SECURITY.md` (inclui endurecimento de `repository_dispatch`).

## 🚀 Pipeline de CI/CD

A atualização dos dados é orquestrada via GitHub Actions com dois workflows:

* **Delivery dedicado:** `.github/workflows/delivery-only.yml` com frequência alvo de 5 min.
* **Financeiro + saldos:** `.github/workflows/main.yml` com frequência menor para não bloquear delivery.
* **Persistence Layer:** o robô commita automaticamente os CSVs atualizados no `master`.

### Scheduler Externo (recomendado para reduzir variação)

O `schedule` do GitHub é *best effort*. Para maior previsibilidade da janela de 5 minutos, dispare o workflow de delivery por API:

1. Crie um token no GitHub com permissão de repositório: **Actions (write)** e **Contents (read)**.
2. (Recomendado, sobretudo em repo público) Crie o secret `EXTERNAL_DISPATCH_TOKEN` no GitHub com um valor aleatório longo.
3. Configure um scheduler externo para chamar a API a cada 5 minutos.

Scripts PowerShell versionados em `scripts/` (logs em `logs/`, ignorados pelo git):

* `scripts/dispatch-delivery.ps1` — dispara `delivery_tick`.
* `scripts/dispatch-delivery-watchdog.ps1` — reforço se o último run atrasar.

Se definir o secret `EXTERNAL_DISPATCH_TOKEN` no GitHub, defina a mesma string na máquina do scheduler como variável de ambiente **`TWILIO_REPO_DISPATCH_SECRET`** (o script envia `client_payload.token`).

Exemplo de request com token (recomendado):

```bash
curl -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer <GITHUB_TOKEN>" \
  https://api.github.com/repos/jmarcilio-tech/twilio-dashboard/dispatches \
  -d "{\"event_type\":\"delivery_tick\",\"client_payload\":{\"token\":\"<MESMO_VALOR_DO_SECRET>\"}}"
```

Exemplo mínimo (compatível apenas enquanto `EXTERNAL_DISPATCH_TOKEN` **não** estiver definido no GitHub):

```bash
curl -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer <GITHUB_TOKEN>" \
  https://api.github.com/repos/jmarcilio-tech/twilio-dashboard/dispatches \
  -d '{"event_type":"delivery_tick"}'
```

Opcionalmente mantenha também o `schedule` do GitHub como fallback.

## 📊 Estrutura dos Datasets

| Arquivo | Nível de Granularidade | Principais Métricas |
| :--- | :--- | :--- |
| `conf_total_marco.csv` | Executivo / Diário | Gasto Total USD, Volume de SMS. |
| `conf_detalhado_marco.csv` | Operacional / Categoria | Custos de Voz, IA, Lookups e Assinaturas. |

## 🛠️ Manutenção e Expansão

Para adicionar uma nova subconta ao monitoramento:

1.  Insira as configurações de `sid`, `token`, `nome` e `categoria` no dicionário `accounts` dentro do script principal.
2.  Configure os respectivos **Secrets** na interface do GitHub (`Settings > Secrets and variables > Actions`).
3.  Mapeie as novas variáveis nos workflows `.github/workflows/main.yml` e `.github/workflows/delivery-only.yml`.

---
*Mantido pela equipe de Engenharia / Data Ops.*