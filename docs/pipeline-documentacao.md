# Twilio Dashboard — Documentação do pipeline e operação

**Repositório:** `jmarcilio-tech/twilio-dashboard` (branch `master`)  
**Última consolidação:** documento gerado para suporte a docs internos / Lovable.

---

## 1. Visão geral

| Área | Descrição |
|------|-----------|
| Objetivo | Automatizar extração Twilio (financeiro, saldos, delivery) e gravar CSVs no GitHub para dashboards |
| Consumidores | Lovable, BI, ou qualquer cliente que leia CSVs raw do GitHub |
| Mudança principal | Workflow **dedicado a delivery** + **scheduler externo** para cadência ~5 min com menor variação que o `schedule` nativo |

---

## 2. Componentes do pipeline

| Nome | Ficheiro / workflow | Saída principal |
|------|---------------------|-----------------|
| Financeiro | `extratorv2.py` + `.github/workflows/main.yml` | `conf_total_marco.csv`, `conf_detalhado_marco.csv` |
| Saldos | `saldo_extractor.py` + `.github/workflows/main.yml` | `conf_saldos.csv` |
| Delivery (rápido ~5 min) | `delivery_extractor.py` + `.github/workflows/delivery-only.yml` | `conf_delivery_stats.csv`, `conf_delivery_horario.csv`, `delivery_sync_state.json` |
| Delivery (varredura diária) | mesmo script + `.github/workflows/delivery-sweep-daily.yml` | append a `conf_delivery_stats_history.csv` (não substitui o snapshot nem o horário) |
| Billing / Usage API | `scripts/fetch_usage_billing_snapshot.py` + `.github/workflows/usage-billing-snapshot.yml` | `conf_usage_billing_snapshot.csv` |

---

## 3. Delivery — modos (`DELIVERY_FETCH_MODE`)

| Modo | Comportamento |
|------|----------------|
| `incremental` | `DateSent>` = agora − `DELIVERY_JANELA_HORAS` (no CI ~5 min: `0.0833333333` h) |
| `baseline_mes` | Desde dia **1** do **mês UTC** até agora (varredura pesada) |
| `baseline_24h` | Últimas **24 h** (teste / comparação com consola) |
| `auto` | Se `delivery_sync_state.json` tem `baseline_month` = mês UTC atual → **incremental**; senão → **baseline_mes** |

---

## 4. Filtro Outgoing (`DELIVERY_DIRECTION`)

| Valor | Efeito |
|--------|--------|
| `outbound` (padrão no CI) | Inclui só mensagens com `direction` começando por `outbound-*` (alinhado a Messaging Insights → **Outgoing**) |
| `all` | Todas as direções (legado) |

---

## 5. Categorias e unidades (delivery)

| Tópico | Detalhe |
|--------|---------|
| Unidade principal | **Segmentos** (`num_segments`) por estado — alinhado ao painel quando a consola usa segmentos |
| Colunas de estado | Delivered, Failed, Undelivered, Sent, Sending, Delivery_Unknown, Accepted, Queued |
| CSV snapshot | `conf_delivery_stats.csv` — inclui `Modo`, `Direcao`, `Extraido_Em`, totais por conta |
| CSV horário | `conf_delivery_horario.csv` — slots **15 min UTC**; append com dedupe `(Slot_15min, Conta)` |
| Migração | Schema antigo de horário → renomeado para `conf_delivery_horario_legacy.csv` quando aplicável |

---

## 6. Workflows GitHub Actions

| Workflow | Ficheiro | Gatilhos | Notas |
|----------|----------|----------|--------|
| Delivery | `delivery-only.yml` | `schedule`, `repository_dispatch` (`delivery_tick`), `workflow_dispatch` | ~5 min; commit de stats + horário + estado; CI pode usar `DELIVERY_LIST_MODE` (ex.: `activity`) |
| Delivery varredura | `delivery-sweep-daily.yml` | `schedule`, `workflow_dispatch` | Janela `since_yesterday_utc`; append histórico; `DELIVERY_STATS_WRITE_SNAPSHOT=0` |
| Billing Usage | `usage-billing-snapshot.yml` | `schedule` (4×/dia UTC), `workflow_dispatch` | Gera/commit `conf_usage_billing_snapshot.csv`; estratégia de datas via inputs/env |
| Financeiro + Saldos | `main.yml` | `schedule`, `workflow_dispatch` | Frequência menor; não corre delivery |

---

## 7. Fiabilidade e agendamento

| Mecanismo | Função |
|-----------|--------|
| `schedule` (GitHub) | Fallback; documentação GitHub: *best effort* (pode atrasar) |
| `repository_dispatch` | Disparo HTTP externo mais previsível |
| Task `TwilioDeliveryDispatch5m` | Executa `scripts/dispatch-delivery.ps1` a cada 5 min |
| Task `TwilioDeliveryWatchdog15m` | Se último run de `delivery-only.yml` atrasar > **12 min**, re-dispara |
| `concurrency` (delivery) | `cancel-in-progress: true` — dois disparos próximos podem gerar run **cancelled** (esperado) |
| `commitar-delivery` | Concorrência para evitar dois `git push` ao mesmo tempo |

---

## 8. Segurança (dispatch e repositório)

| Item | Descrição |
|------|-----------|
| `EXTERNAL_DISPATCH_TOKEN` | Secret no GitHub; quando definido, `repository_dispatch` deve trazer `client_payload.token` igual |
| `TWILIO_REPO_DISPATCH_SECRET` | Mesmo valor na máquina do scheduler (env); o script inclui no payload |
| Validação no workflow | Step em shell + `jq` sobre `GITHUB_EVENT_PATH` (evita `if:` com `secrets` — causava falhas 0s em `push`) |
| `SECURITY.md` | Política, rotação, boas práticas |
| `dependabot.yml` | Atualização semanal de dependências pip |
| `.gitignore` | `.env`, `.env.*`, `logs/`, `*.log` |
| `scripts/setup-dispatch-secret.ps1` | Gera token e instrui configuração sem gravar no repo |

---

## 9. Scripts Windows (no repositório)

| Script | Função |
|--------|--------|
| `scripts/dispatch-delivery.ps1` | `POST /repos/.../dispatches` com `event_type=delivery_tick` e token opcional |
| `scripts/dispatch-delivery-watchdog.ps1` | Consulta último run (`gh run list`) e re-dispara se necessário |
| `scripts/setup-dispatch-secret.ps1` | Gera token e guia GitHub + `setx` |

---

## 10. Lovable / dashboard — uma fonte por ecrã (obrigatório)

| Ecrã / métrica | Ficheiro único | Nunca misturar com |
|----------------|----------------|---------------------|
| **Outgoing / delivery ao vivo** (Messaging Insights, ~janela do job) | `conf_delivery_stats.csv` | Não somar `conf_delivery_horario.csv` para o mesmo “headline total”; não usar `conf_delivery_stats_history.csv` como número atual |
| **Gráfico 15 min / heatmap dia** | `conf_delivery_horario.csv` (slots UTC) | Não usar como substituto do total da consola sem filtrar o dia e sem clarificar que é série agregada por slot |
| **Série / tendência larga** (ontem 00:00 UTC → agora, append diário) | `conf_delivery_stats_history.csv` | Não apresentar como snapshot “agora”; cada linha é uma execução/janela gravada no histórico |
| **Total Spend / SMS Usage / preço (Account Insights, dia GMT)** | `conf_usage_billing_snapshot.csv` | Não comparar diretamente com totais do snapshot de delivery (API e janela diferentes) |
| **Saúde do pipeline** | `delivery_sync_state.json` | Metadados apenas (ex.: `last_run_utc`, `api_pages_by_account`) |

**Regras de leitura**

- Usar **nomes de colunas** (cabeçalho CSV), não índices fixos — o schema pode evoluir.
- **Segmentos** vs **mensagens**: no delivery, estados principais (`Delivered`, `Failed`, …) são por **segmentos**; colunas `Insight_*` são contagens por **mensagem** (legenda “Delivery & Errors” aproximada).
- Mostrar sempre **UTC** na UI quando a fonte for UTC (`Extraido_Em`, `Agregado_Ate_Utc`, `Slot_15min`, `Extraido_Utc` no billing).
- Se `Api_Pages_Capped` = 1, avisar que a lista API pode estar truncada (modo `activity`); sugerir revisão operacional, não “corrigir” números no cliente.

**Cabeçalho `conf_delivery_stats.csv` / histórico** (mesmo schema):

`Conta`, `Categoria`, `Janela`, `Modo`, `Direcao`, `List_Mode`, `Mensagens`, `Segmentos`, + estados (`Delivered` … `Queued`), `Taxa_Entrega_%`, `Insight_Delivered_Msgs`, `Insight_Failed_Msgs`, `Insight_Delivery_Unknown_Msgs`, `Insight_Undelivered_Msgs`, `Insight_Sent_Msgs`, `Insight_Total_Msgs`, `Api_Pages`, `Api_Pages_Capped`, `Agregado_Ate_Utc`, `Github_Run_Id`, `Extraido_Em`.

**Cabeçalho `conf_usage_billing_snapshot.csv`:**

`Conta`, `Range`, `TotalPrice_Totalprice`, `SMS_Count`, `SMS_Usage`, `SMS_Price`, `Sum_Price_NoTotalprice`, `SMS_Subcategories_Sample`, `Extraido_Utc`.  
Linha agregada org: `Conta` = `__ORG_SUM__`.

---

## 10.1 Prompt para colar na Lovable (alinhamento Twilio)

Copiar o bloco abaixo para o projeto Lovable (ajustar apenas URL raw do GitHub se necessário).

```
Contexto: dashboard alimentado por CSVs commitados no repositório GitHub jmarcilio-tech/twilio-dashboard (branch master). Os dados são produzidos por pipelines Python + GitHub Actions; não há Twilio no browser.

Regra de ouro — UMA fonte por vista:
1) KPIs de messaging / outgoing em tempo quase real: ler só conf_delivery_stats.csv. É um snapshot por execução (~5 min): coluna Janela descreve a janela (ex. 4min ou since_yesterday_utc_*). Não somar conf_delivery_horario.csv para obter o mesmo número que este snapshot.
2) Gráficos por intervalo de 15 minutos (UTC): conf_delivery_horario.csv — cabeçalho inclui Slot_15min, Conta, Categoria, estados por segmento, Total_Slot.
3) Histórico / séries longas (varredura diária): conf_delivery_stats_history.csv — mesmo schema que conf_delivery_stats.csv mas append ao longo do tempo; não usar como valor “atual” da conta sem filtrar pela última linha ou pelo Github_Run_Id/Extraido_Em desejados.
4) Billing próximo da consola Account Insights (Usage Records, granularidade dia GMT): conf_usage_billing_snapshot.csv. A consola “Last 24 hours” é janela rolante; o CSV usa estratégia documentada no workflow (default end_utc_day = dia civil UTC corrente). Para “SMS Transactions” comparar SMS_Count vs SMS_Usage com o card da Twilio (usage costuma refletir segmentos).
5) Estado operacional (último run, páginas API): delivery_sync_state.json — só metadados/health, não misturar com totais de billing.

Implementação UI:
- Fetch CSV raw (cache curto, ex. 60–120s). Parse por cabeçalho.
- Rótulos: sempre indicar fonte (“Snapshot delivery”, “Slots 15 min UTC”, “Histórico pipeline”, “Billing Usage API”) e timezone UTC onde aplicável.
- Se Api_Pages_Capped=1 numa conta, mostrar aviso de dados possivelmente truncados.
- Não expor secrets; URL do repo pode ser pública read-only.

Não fazer: misturar totais de conf_delivery_horario com conf_delivery_stats no mesmo KPI; assumir que Mensagens e Segmentos são intercambiáveis; comparar billing Last-24h rolante com um único dia UTC sem explicar a diferença.
```

---

## 11. Diferenças conhecidas vs Twilio Console

| Tópico | Nota |
|--------|------|
| Motor | Consola Insights = analytics; extrator = REST Messages + regras explícitas |
| Unidades | Comparar **segmentos** com **segmentos**; não misturar com total de **mensagens** |
| Tempo | “Past 24h” ≠ “ontem UTC” ≠ janela móvel 5 min |
| Âmbito | Uma conta na consola vs uma linha por conta no CSV; soma global ≠ uma conta |

---

## 12. Backlog / follow-up opcional

| # | Item |
|---|------|
| 1 | Restringir `delivery-only.yml` a `master` + eventos desejados (menos ruído em PRs Dependabot) |
| 2 | Alertas se lag elevado por N ciclos consecutivos |
| 3 | Métricas (duração média do job, taxa de cancelamento) |
| 4 | Tabela oficial API status → colunas CSV no README |
| 5 | Testes unitários mínimos no `delivery_extractor` |

---

## 13. Verificações operacionais (referência)

| Verificação | Resultado esperado |
|-------------|---------------------|
| Últimos `delivery_tick` em `master` | `success` em cadência ~5 min |
| `delivery_sync_state.json` | `last_run_utc` atualizado após sucesso |
| Tasks Windows | Último resultado `0` |
| Runs `cancelled` | Possível por concorrência — não indica falha de dados |
| Falhas `0s` em `push` antigas | Histórico de correção de YAML — não confundir com estado atual do extrator |

---

## 14. Conversão para DOCX

Se tiver **Pandoc** instalado:

```bash
pandoc docs/pipeline-documentacao.md -o docs/pipeline-documentacao.docx
```

Caso contrário, abrir este `.md` no Word / Google Docs (importar ficheiro) ou colar o conteúdo e aplicar estilos de título manualmente.
