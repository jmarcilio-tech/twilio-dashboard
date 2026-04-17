# Dashboard Lovable — 3 abas isoladas (fonte única por aba)

Este ficheiro é o **contrato único** para o layout em três separadores: cada aba consome apenas os CSVs listados para ela. Os outros documentos em `docs/lovable-*` são **fragmentos de código** ou histórico — usar este para prompts e decisões de dados.

## Frontend Lovable (alinhamento)

| Ambiente | URL |
|----------|-----|
| **Preview** (requer login na Lovable) | https://id-preview--67b6da5f-38bc-410b-95eb-0783b08a490e.lovable.app |
| **Publicado** (domínio público após Publish) | https://twilio-intelligence.lovable.app |
| **Projeto no editor** | https://lovable.dev/projects/67b6da5f-38bc-410b-95eb-0783b08a490e |

**Nota:** o preview pode divergir do publicado até fazer **Publish**; para validar o que os utilizadores veem, usa o URL publicado.

### Contas (nomes e ordem = coluna `Conta` nos CSVs)

- **Fonte no repo:** `data/accounts_canonical.json` (ordem fixa, categorias Recuperação / Broadcast / Standby).
- **Raw no GitHub (allowlist no `csv-proxy` se usado):** `.../master/data/accounts_canonical.json`
- **Regras na UI:** (1) Preencher dropdowns e gráficos com `account_order` (não hardcode parcial de 3 contas). (2) `__ORG_SUM__` no snapshot de billing = totais agregados; excluir do seletor de contas. (3) Nomes **exatamente** como no JSON (ex.: `Joao`, não `João`).

O Python do pipeline lê a mesma ordem a partir de `accounts_catalog.py` (um único sítio — evita desalinhamento com a Lovable).

---

## Visão geral

| Aba sugerida | Propósito | CSVs permitidos (não misturar com as outras abas) |
|--------------|-----------|---------------------------------------------------|
| **1 — Billing / Gasto** | Spend e uso por conta (Usage API); **gasto total da org** | `conf_usage_billing_snapshot.csv` (+ opcionais na mesma aba: `by_category`, `daily`, `month/` conforme filtros) |
| **2 — Delivery & mensagens** | Estados de envio, janelas REST/Insights, séries 15 min | `conf_delivery_stats.csv`, `conf_delivery_insights_4h.csv`, `conf_delivery_horario.csv`, `conf_delivery_insights_timeseries.csv`, `conf_delivery_stats_history.csv`, `delivery_sync_state.json` |
| **3 — Financeiro (executivo)** | Totais detalhados da API financeira clássica / saldos | `conf_total_marco.csv`, `conf_detalhado_marco.csv`, `conf_saldos.csv` |

**Regra:** KPIs da aba 1 não usam ficheiros da aba 2 nem 3; KPIs de delivery não usam `conf_usage_billing_*`.

---

## Aba 1 — Billing / Gasto

**Fonte obrigatória para números de Usage API:** `conf_usage_billing_snapshot.csv` (branch `master`).

### Gasto total (cartão principal)

- Usar a linha em que **`Conta === "__ORG_SUM__"`** e o campo **`TotalPrice_Totalprice`** como **total de gasto USD** da organização na janela descrita em **`Range`**.
- Alternativa equivalente (se `__ORG_SUM__` falhar): somar **`TotalPrice_Totalprice`** apenas das linhas de contas reais (excluir `__ORG_SUM__` para não duplicar). Preferir sempre a linha agregada quando existir.

### Por conta

- Uma linha por conta (NS, Joao, …); excluir `__ORG_SUM__` do seletor de “conta individual”.
- Mostrar sempre **`Range`** e **`Extraido_Utc`** visíveis (subtítulo ou info).

### Opcionais **nesta mesma aba** (sub-secções)

- Tabela hierárquica por categoria: **`conf_usage_billing_by_category.csv`** (mesmo job / mesma janela que o snapshot quando `cover_days` ou mesmo intervalo de datas).
- Gráfico diário: **`conf_usage_billing_daily.csv`** ou caminho **`month/conf_usage_billing_*.csv`** quando a UI estiver em modo “mês civil” — não misturar séries com cartões vindos de `conf_delivery_*`.

Fragmentos de referência: `docs/lovable-usage-summary-tab.md`, `docs/lovable-usage-hybrid/README.md`.

---

## Aba 2 — Delivery & mensagens

Usar apenas os CSVs de messaging listados na secção **10** de `docs/pipeline-documentacao.md` (Outgoing rápido vs Insights 4h vs horário vs timeseries vs histórico). **Não** usar `conf_usage_billing_snapshot.csv` nesta aba para total spend ou SMS price.

Fragmentos de referência: `docs/lovable-delivery-sync/README.md`.

---

## Aba 3 — Financeiro

- **`conf_total_marco.csv`** — visão executiva agregada.
- **`conf_detalhado_marco.csv`** — detalhe por categoria/linha de serviço conforme schema do pipeline.
- **`conf_saldos.csv`** — saldos quando aplicável.

Não tratar estes totais como paridade direta com **`TotalPrice_Totalprice`** da aba 1 (motores e janelas diferentes).

---

## Variáveis de ambiente / config (Lovable)

**No browser:** não colocar secrets Twilio; só URLs públicas ou **Supabase Edge `csv-proxy`** com paths allowlist.

Sugestão mínima por aba:

| Aba | Variáveis conceituais | Notas |
|-----|------------------------|--------|
| 1 | `GITHUB_RAW_BASE` ou URL fixa raw + paths `conf_usage_billing_*.csv` | Incluir `month/` apenas se a UI tiver modo mês |
| 2 | Mesma base + paths `conf_delivery_*`, `delivery_sync_state.json` | Allowlist cada ficheiro no proxy |
| 3 | Paths `conf_total_marco.csv`, `conf_detalhado_marco.csv`, `conf_saldos.csv` | Opcional se a app não tiver o separador |

Variáveis **do pipeline** (`USAGE_DATE_STRATEGY`, `DELIVERY_*`, etc.) pertencem ao GitHub Actions, **não** ao frontend — não listar no prompt da Lovable salvo para documentar o que gera cada CSV.

---

## Documentos que **não** são segunda “fonte de verdade”

| Ficheiro | Função |
|----------|--------|
| `docs/pipeline-documentacao.md` | Referência técnica completa (schema, workflows) |
| `docs/lovable-dashboard-3-abas.md` | **Este** — divisão em 3 abas e KPIs |
| `docs/lovable-usage-summary-tab.md` | Prompt detalhado só aba Usage / snapshot |
| `docs/lovable-usage-hybrid/` | Código exemplo + by_category |
| `docs/lovable-delivery-sync/` | Código exemplo Delivery |
| `docs/Pipeline.md` | Checklist interno de tarefas, não especificação de UI |

Para evitar confusão no assistente ao colar prompts: **anexar primeiro** o resumo das 3 abas deste ficheiro; só depois fragmentos de código se necessário.
