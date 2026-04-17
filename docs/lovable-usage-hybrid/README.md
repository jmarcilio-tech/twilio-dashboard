# Usage híbrido (snapshot + por categoria) — referência Lovable

Copiar ficheiros desta pasta para o projeto Lovable (ajustar `@/` e componentes UI).

## Pipeline (repo `twilio-dash`)

| Ficheiro | Descrição |
|----------|-----------|
| `conf_usage_billing_snapshot.csv` | Resumo por conta (`TotalPrice_Totalprice`, SMS, …) |
| `conf_usage_billing_by_category.csv` | **Uma linha por (Conta, Categoria)** — todas as categorias `Usage/Records` agregadas na mesma janela que o snapshot |

Raw (exemplo):

- `https://raw.githubusercontent.com/jmarcilio-tech/twilio-dashboard/master/conf_usage_billing_snapshot.csv`
- `https://raw.githubusercontent.com/jmarcilio-tech/twilio-dashboard/master/conf_usage_billing_by_category.csv`

**Nota `rolling_24h_proxy`:** os cartões do snapshot usam *blend* por hora (~Last 24h); o CSV por categoria usa a **soma das linhas da API** nos dias UTC `StartDate…EndDate` que intersectam a janela — os totais por categoria podem diferir ligeiramente do `TotalPrice_Totalprice` do cartão.

## Ficheiros aqui

| Origem | Destino típico |
|--------|------------------|
| `src/lib/usage-billing-by-category.ts` | `src/lib/usage-billing-by-category.ts` |
| `src/components/UsageBillingTab.tsx` | fundir com a guia Usage |
| `supabase/csv-proxy-fragment.md` | instruções para allowlist |

## csv-proxy

Adicionar ao allowlist o path **`conf_usage_billing_by_category.csv`** (nome canónico no repo; na Lovable podes expor como `usage_billing_by_category` no payload se quiseres).

## UI

- **Sempre:** cartões a partir do snapshot (mesmo sem por-categoria).
- **Se o fetch do por-categoria falhar ou CSV vazio:** `Alert` a explicar que o job ainda não gerou o ficheiro ou falhou; tabela omitida.
- **Se existir:** tabela colapsável por hierarquia de prefixos (`sms` → `sms-outbound` → …), estilo consola.
