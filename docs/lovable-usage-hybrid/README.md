# Usage híbrido (snapshot + por categoria) — referência Lovable

Copiar ficheiros desta pasta para o projeto Lovable (ajustar `@/` e componentes UI).

## Pipeline (repo `twilio-dash`)

| Ficheiro | Descrição |
|----------|-----------|
| `conf_usage_billing_snapshot.csv` | Resumo por conta (`TotalPrice_Totalprice`, SMS, …) |
| `conf_usage_billing_by_category.csv` | **Uma linha por (Conta, Categoria)** — todas as categorias `Usage/Records` agregadas na mesma janela que o snapshot |
| `conf_usage_billing_daily.csv` | **Uma linha por (Conta, dia UTC, Categoria)** — série diária via `/Daily` (default `totalprice` + `sms` para gráficos de spend e volume) |

Raw (exemplo):

- `https://raw.githubusercontent.com/jmarcilio-tech/twilio-dashboard/master/conf_usage_billing_snapshot.csv`
- `https://raw.githubusercontent.com/jmarcilio-tech/twilio-dashboard/master/conf_usage_billing_by_category.csv`
- `https://raw.githubusercontent.com/jmarcilio-tech/twilio-dashboard/master/conf_usage_billing_daily.csv`

**Workflow GitHub:** em *Run workflow* podes usar **`billing_month`** (`AAAA-MM`) ou **`usage_start_date`** + **`usage_end_date`** para gerar os três CSVs alinhados a um **mês civil** (ou intervalo) — o mesmo `Range` aparece em todos.

**Default `cover_days`:** snapshot e por-categoria somam os **mesmos** dias civis UTC (~24h); **SMS_Count** aproxima o cartão **SMS Transactions** do Account Insights. **`rolling_24h_proxy`** (legado): blend por hora no cartão — subestima transações vs Insights; por-categoria já era soma por dias.

## Ficheiros aqui

| Origem | Destino típico |
|--------|------------------|
| `src/lib/usage-billing-by-category.ts` | `src/lib/usage-billing-by-category.ts` |
| `src/lib/usage-billing-daily.ts` | parser tipado para o CSV diário |
| `src/components/UsageBillingTab.tsx` | fundir com a guia Usage |
| `supabase/csv-proxy-fragment.md` | instruções para allowlist |

## csv-proxy

Adicionar ao allowlist o path **`conf_usage_billing_by_category.csv`** (nome canónico no repo; na Lovable podes expor como `usage_billing_by_category` no payload se quiseres).

## UI

- **Sempre:** cartões a partir do snapshot (mesmo sem por-categoria).
- **Callout temporal:** explicar que o CSV é um snapshot no `Extraido_Utc`; a Twilio Console pode mostrar mais uso se consultada horas depois — a UI deve refletir o CSV, não "ajustar" à consola.
- **Se o fetch do por-categoria falhar ou CSV vazio:** `Alert` a explicar que o job ainda não gerou o ficheiro ou falhou; tabela omitida.
- **Se existir:** tabela colapsável por hierarquia de prefixos (`sms` → `sms-outbound` → …), estilo consola.
