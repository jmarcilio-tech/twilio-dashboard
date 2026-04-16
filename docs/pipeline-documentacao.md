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
| Delivery | `delivery_extractor.py` + `.github/workflows/delivery-only.yml` | `conf_delivery_stats.csv`, `conf_delivery_horario.csv`, `delivery_sync_state.json` |

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
| Delivery | `delivery-only.yml` | `schedule`, `repository_dispatch` (`delivery_tick`), `workflow_dispatch` | ~5 min; commit só de ficheiros de delivery |
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

## 10. Lovable / dashboard — requisitos documentados

| Tema | Implementação sugerida |
|------|-------------------------|
| Fonte de dados | Raw: `conf_delivery_stats.csv`, `conf_delivery_horario.csv`, `delivery_sync_state.json` |
| Saúde da coleta | `last_run_utc`, lag em minutos (UTC), estados Saudável / Atenção / Atrasado |
| KPIs | **Janela móvel 5 min** (snapshot) vs **Acumulado do dia UTC** (soma slots do dia no horário) |
| Fallback | Snapshot vazio → último válido com badges e níveis de confiança |
| Segurança | Sem secrets no browser; allowlist de URLs; cache/TTL; rate limit; CORS |
| QA | Checklist de testes (lag, troca de conta, UTC, acumulado estável, etc.) |

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
