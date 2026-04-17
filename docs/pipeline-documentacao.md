# Twilio Dashboard — Documentação do pipeline e operação

**Repositório:** `jmarcilio-tech/twilio-dashboard` (branch `master`)  
**Última consolidação:** documento gerado para suporte a docs internos / Lovable.

**Checklist para apresentação / acompanhamento:** [docs/Pipeline.md](./Pipeline.md)

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
| Saldos | `saldo_extractor.py` + `.github/workflows/saldo-only.yml` | `conf_saldos.csv` |
| Delivery (rápido ~5 min) | `delivery_extractor.py` + `.github/workflows/delivery-only.yml` | `conf_delivery_stats.csv`, `conf_delivery_horario.csv`, `delivery_sync_state.json` |
| Delivery (varredura diária) | mesmo script + `.github/workflows/delivery-sweep-daily.yml` | append a `conf_delivery_stats_history.csv` (não substitui o snapshot nem o horário) |
| Delivery Insights (Past N h, consola) | `scripts/fetch_delivery_insights_snapshot.py` + `.github/workflows/delivery-insights-4h.yml` | `conf_delivery_insights_4h.csv` (mensagens + segmentos; `activity` + outbound) |
| Billing / Usage API | `scripts/fetch_usage_billing_snapshot.py` + `.github/workflows/usage-billing-snapshot.yml` | `conf_usage_billing_snapshot.csv`, `conf_usage_billing_by_category.csv`, `conf_usage_billing_daily.csv` |

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
| CSV Insights (Past 4h) | `conf_delivery_insights_4h.csv` — colunas `Insight_*` (mensagens, legenda 5 estados) + `*_Seg`; alinhado à aba **Delivery & Errors** da consola (aprox. REST) |
| CSV horário | `conf_delivery_horario.csv` — slots **15 min UTC**; append com dedupe `(Slot_15min, Conta)` |
| CSV Insights timeseries (15 min) | `conf_delivery_insights_timeseries.csv` — mensagens por slot (`Insight_*`), mesmo `Slot_15min` UTC que o horário; script `scripts/fetch_delivery_insights_timeseries.py` + workflow `delivery-insights-timeseries.yml` |
| Migração | Schema antigo de horário → renomeado para `conf_delivery_horario_legacy.csv` quando aplicável |

---

## 6. Workflows GitHub Actions

| Workflow | Ficheiro | Gatilhos | Notas |
|----------|----------|----------|--------|
| Saldos (rápido ~5 min) | `saldo-only.yml` | `schedule`, `repository_dispatch` (`saldo_tick`), `workflow_dispatch` | `conf_saldos.csv` apenas; leve |
| Delivery | `delivery-only.yml` | `schedule`, `repository_dispatch` (`delivery_tick`), `workflow_dispatch` | ~5 min; commit de stats + horário + estado; CI pode usar `DELIVERY_LIST_MODE` (ex.: `activity`) |
| Delivery varredura | `delivery-sweep-daily.yml` | `schedule`, `workflow_dispatch` | Janela `since_yesterday_utc`; append histórico; `DELIVERY_STATS_WRITE_SNAPSHOT=0` |
| Delivery Insights 4h | `delivery-insights-4h.yml` | `schedule` (2×/h UTC), `workflow_dispatch` | Gera/commit `conf_delivery_insights_4h.csv`; inputs `insights_hours`, `list_mode` |
| Delivery Insights timeseries | `delivery-insights-timeseries.yml` | `schedule` (2×/h UTC), `workflow_dispatch` | Gera/commit `conf_delivery_insights_timeseries.csv`; inputs `ts_hours`, `list_mode` |
| Billing Usage | `usage-billing-snapshot.yml` | `schedule` (4×/dia UTC), `workflow_dispatch` | Gera/commit snapshot + por categoria + **diário**; inputs opcionais `billing_month` (AAAA-MM), `usage_start_date` / `usage_end_date` (GMT), `usage_test_account` (ex. `richard` — só com intervalo fixo; grava em `month/`) |
| Financeiro | `main.yml` | `schedule`, `workflow_dispatch` | Só `conf_total_marco.csv` / `conf_detalhado_marco.csv`; não corre delivery nem saldos |

---

## 7. Fiabilidade e agendamento

| Mecanismo | Função |
|-----------|--------|
| `schedule` (GitHub) | Fallback; documentação GitHub: *best effort* (pode atrasar) |
| `repository_dispatch` | Disparo HTTP externo mais previsível |
| Task `TwilioDeliveryDispatch5m` | Executa `scripts/dispatch-delivery.ps1` a cada 5 min |
| Task `TwilioSaldoDispatch5m` (opcional) | Executa `scripts/dispatch-saldo.ps1` a cada 5 min — mesmo token que delivery; cadência mais estável que só o `schedule` do GitHub |
| Task `TwilioDeliveryWatchdog15m` | Se último run de `delivery-only.yml` atrasar > **12 min**, re-dispara |
| `concurrency` (delivery) | `cancel-in-progress: true` — dois disparos próximos podem gerar run **cancelled** (esperado) |
| `concurrency` (saldos) | Igual ao delivery: run e commit com `cancel-in-progress: true` — prioriza o snapshot mais recente |
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
| `scripts/dispatch-saldo.ps1` | Idem com `event_type=saldo_tick` |
| `scripts/dispatch-delivery-watchdog.ps1` | Consulta último run (`gh run list`) e re-dispara se necessário |
| `scripts/setup-dispatch-secret.ps1` | Gera token e guia GitHub + `setx` |

---

## 10. Lovable / dashboard — uma fonte por ecrã (obrigatório)

**Resumo para UI em 3 separadores (Billing vs Delivery vs Financeiro):** ver **`docs/lovable-dashboard-3-abas.md`** — evita misturar CSVs entre abas e define **gasto total** = `TotalPrice_Totalprice` na linha `__ORG_SUM__`.

| Ecrã / métrica | Ficheiro único | Nunca misturar com |
|----------------|----------------|---------------------|
| **Outgoing / operação rápida (~5 min)** | `conf_delivery_stats.csv` | Não somar `conf_delivery_horario.csv` para o mesmo “headline total”; não usar `conf_delivery_stats_history.csv` como número atual |
| **Delivery & Errors (Past 4h, consola)** | `conf_delivery_insights_4h.csv` | Não usar `conf_delivery_stats.csv` para os mesmos cartões (janela e API diferentes); ver colunas `Insight_*` e `Insights_Hours` |
| **Gráfico 15 min / heatmap dia** | `conf_delivery_horario.csv` (slots UTC) | Não usar como substituto do total da consola sem filtrar o dia e sem clarificar que é série agregada por slot |
| **Evolução Delivery — mensagens por janela (UI)** | `conf_delivery_insights_timeseries.csv` | REST **Messages.json** (não é Usage “Daily”). CI: matrix 8 contas + merge. **Fatias (`DELIVERY_INSIGHTS_TS_CHUNK_HOURS`, default 4 h):** a janela `DELIVERY_INSIGHTS_TS_HOURS` é cortada em fatias; **paginação / MAX_PAGES reinicia por fatia** (~2,5M msgs/fatia) para suportar contas com **milhões** de envios na janela; `CHUNK_HOURS=0` desativa (um só loop — não usar em contas gigantes). |
| **Série / tendência larga** (ontem 00:00 UTC → agora, append diário) | `conf_delivery_stats_history.csv` | Não apresentar como snapshot “agora”; cada linha é uma execução/janela gravada no histórico |
| **Total Spend / SMS (~Last 24h Insights)** | `conf_usage_billing_snapshot.csv` | Default **`cover_days`** (soma **Usage/Records** nos dias civis UTC tocados pela janela ~24h; alinha **SMS_Count** ao cartão **SMS Transactions** do Insights). `rolling_24h_proxy` = blend horário (legado; subestima transações). **Total Spend** do Insights ≠ garantido `TotalPrice_Totalprice`. Não misturar com delivery |
| **Usage por categoria (tabela / hierarquia)** | `conf_usage_billing_by_category.csv` | Mesmo job que o snapshot; colunas `Conta`, `Categoria`, `Count`, `Usage`, `Price_USD`, `Range`, `Extraido_Utc`. Com `cover_days`, snapshot e por-categoria usam o mesmo recorte de dias UTC. UI: `docs/lovable-usage-hybrid/` |
| **Usage diário (gráficos / visão geral)** | `conf_usage_billing_daily.csv` | Endpoint `/Daily` por categoria (`totalprice`, `sms` por defeito); uma linha por `(Conta, dia, categoria)`. Intervalo = mesma janela GMT que o snapshot (ex. mês com `USAGE_START_DATE`/`USAGE_END_DATE` ou 1–2 dias em `cover_days`). Limite `USAGE_DAILY_MAX_SPAN_DAYS` (default 366). |
| **Usage mês civil (ficheiros estáveis)** | `month/conf_usage_billing_snapshot.csv` (+ by_category + daily) | Gravados **só** em runs com intervalo fixo (`billing_month` ou `usage_start_date`+`usage_end_date`). O cron rolling continua a atualizar só a **raiz**. Raw: `.../master/month/conf_usage_billing_snapshot.csv` |
| **Saúde do pipeline** | `delivery_sync_state.json` | Metadados apenas (ex.: `last_run_utc`, `api_pages_by_account`) |

**Regras de leitura**

- Usar **nomes de colunas** (cabeçalho CSV), não índices fixos — o schema pode evoluir.
- **Segmentos** vs **mensagens**: em `conf_delivery_stats.csv` os estados principais são por **segmentos**; `Insight_*` são por **mensagem**. Em **`conf_delivery_insights_4h.csv`** use `Insight_*` para a legenda **Delivery & Errors** (mensagens) e `*_Seg` para volume em segmentos.
- Mostrar sempre **UTC** na UI quando a fonte for UTC (`Extraido_Em`, `Agregado_Ate_Utc`, `Slot_15min`, `Extraido_Utc` no billing).
- Se `Api_Pages_Capped` = 1, avisar que a lista API pode estar truncada (modo `activity`); sugerir revisão operacional, não “corrigir” números no cliente.
- **Timeseries vs consola:** o gráfico Twilio **Delivery & Errors** usa agregação interna; o CSV vem de **REST Messages** + slot 15 min. Totais só coincidem na ordem de grandeza se a paginação cobrir **todas** as mensagens da janela; estados **Queued** na consola podem ir parcialmente para **`Insight_Delivery_Unknown_Msgs`** (legenda Insight 5 do script).

**Cabeçalho `conf_delivery_stats.csv` / histórico** (mesmo schema):

`Conta`, `Categoria`, `Janela`, `Modo`, `Direcao`, `List_Mode`, `Mensagens`, `Segmentos`, + estados (`Delivered` … `Queued`), `Taxa_Entrega_%`, `Insight_Delivered_Msgs`, `Insight_Failed_Msgs`, `Insight_Delivery_Unknown_Msgs`, `Insight_Undelivered_Msgs`, `Insight_Sent_Msgs`, `Insight_Total_Msgs`, `Api_Pages`, `Api_Pages_Capped`, `Agregado_Ate_Utc`, `Github_Run_Id`, `Extraido_Em`.

**Cabeçalho `conf_delivery_insights_4h.csv`** (snapshot Insights; uma linha por conta):

`Conta`, `Categoria`, `Insights_Hours`, `List_Mode`, `Direcao`, `Janela_Inicio_Utc`, `Janela_Fim_Utc`, `Insight_Delivered_Msgs`, `Insight_Failed_Msgs`, `Insight_Undelivered_Msgs`, `Insight_Sent_Msgs`, `Insight_Delivery_Unknown_Msgs`, `Insight_Total_Msgs`, `Mensagens`, `Segmentos`, `Delivered_Seg` … `Queued_Seg`, `Api_Pages`, `Api_Pages_Capped`, `Github_Run_Id`, `Extraido_Utc`.

**Cabeçalho `conf_usage_billing_snapshot.csv`:**

`Conta`, `Range`, `TotalPrice_Totalprice`, `SMS_Count`, `SMS_Usage`, `SMS_Price`, `Sum_Price_NoTotalprice`, `SMS_Subcategories_Sample`, `Extraido_Utc`.  
Linha agregada org: `Conta` = `__ORG_SUM__`.

---

## 10.1 Prompt para colar na Lovable (atualizar dashboard + novos valores billing)

Copiar o bloco abaixo para o projeto Lovable (Twilio Intelligence Dashboard). Ajustar só se o branch ou o owner do repo mudarem.

```
Atualiza o Twilio Intelligence Dashboard para consumir os CSVs do GitHub e alinhar os números com a Twilio Console conforme abaixo.

## URLs raw (branch master)
Base: https://raw.githubusercontent.com/jmarcilio-tech/twilio-dashboard/master/
- conf_delivery_stats.csv
- conf_delivery_insights_4h.csv
- conf_delivery_horario.csv
- conf_delivery_stats_history.csv
- conf_usage_billing_snapshot.csv
- delivery_sync_state.json
(opcional financeiro: conf_total_marco.csv, conf_detalhado_marco.csv, conf_saldos.csv)

## Regra de ouro — UMA fonte por ecrã
1) Operação / snapshot rápido (~5 min, pipeline delivery): SÓ conf_delivery_stats.csv. Coluna Janela descreve a janela. NÃO somar conf_delivery_horario.csv para o mesmo headline total.
2) Aba estilo Twilio “SMS > Insights > Delivery & Errors” (Past 4 hours, Outgoing, contagens por mensagem na legenda de 5 estados): SÓ conf_delivery_insights_4h.csv. Ler Insights_Hours (ex. 4), Janela_Inicio_Utc / Janela_Fim_Utc, Extraido_Utc. Cartões Total Outgoing / Delivered / Failed / Undelivered / Sent / Delivery Unknown → colunas Insight_Delivered_Msgs, Insight_Failed_Msgs, Insight_Undelivered_Msgs, Insight_Sent_Msgs, Insight_Delivery_Unknown_Msgs, Insight_Total_Msgs. Para volume em segmentos usar Delivered_Seg, Failed_Seg, … ou coluna Segmentos. NÃO usar conf_delivery_stats.csv para estes mesmos cartões (janela e definição diferentes).
3) Gráfico 15 min UTC: conf_delivery_horario.csv (Slot_15min, segmentos por estado, Total_Slot).
4) Tendência longa (varredura diária): conf_delivery_stats_history.csv — append; NÃO usar como “valor agora” sem filtrar por Extraido_Em / Github_Run_Id.
5) Account Insights / Billing (~Last 24h): SÓ conf_usage_billing_snapshot.csv (default **cover_days**; coluna `Range`). NÃO misturar com delivery.
6) Saúde do pipeline: delivery_sync_state.json (metadados).

## Billing — cartões “Last 24 hours”
- Total Spend → TotalPrice_Totalprice (linha por conta; **total org** na linha `__ORG_SUM__`)
- Programmable SMS Spend → SMS_Price
- SMS Transactions → SMS_Usage (principal); SMS_Count como secundário/tooltip
- Badge: texto da coluna **Range** + **Extraido_Utc** (default **`cover_days`** — dias civis UTC na janela; ver workflow; legado **`rolling_24h_proxy`** = blend horário)

## Implementação técnica
- Fetch GET aos raw URLs; cache 60–120s; parse por cabeçalho.
- Sem Twilio SDK nem secrets no browser.

## Não fazer
- Misturar conf_delivery_insights_4h com conf_delivery_stats no mesmo conjunto de KPIs “Delivery & Errors”.
- Misturar conf_delivery_horario + conf_delivery_stats num único headline de total outgoing.
- Tratar billing ou insights CSV como paridade pixel-perfect com a consola (aproximações documentadas).
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
