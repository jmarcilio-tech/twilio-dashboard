# Sincronizar aba Delivery (Lovable) com janela do gráfico

Copie os ficheiros desta pasta para o projeto Lovable **mantendo os caminhos** `src/...` e `supabase/...`.

## Pipeline (repo twilio-dash)

1. `conf_delivery_horario.csv` — já existente (segmentos por slot).
2. **`conf_delivery_insights_timeseries.csv`** — novo; mensagens por slot (Insight 5).  
   - Script: `scripts/fetch_delivery_insights_timeseries.py`  
   - Workflow: `.github/workflows/delivery-insights-timeseries.yml`  
   - Raw: `https://raw.githubusercontent.com/jmarcilio-tech/twilio-dashboard/master/conf_delivery_insights_timeseries.csv`

## O que mudou na UI

- Legenda lateral e **Total** do header usam totais **derivados dos dados filtrados pela mesma janela do gráfico** (`chartTotals` / `chartGrandTotal`), a partir de `conf_delivery_horario.csv` (segmentos).
- **Removido** `past4hTotals` / `conf_delivery_insights_4h.csv` da secção “Evolução de Delivery” (evita números congelados).
- `conf_delivery_insights_4h.csv` pode continuar noutro ecrã (card “Past 4h” fixo), se desejarem.
- Se existir `insightsTimeseries`, mostrar toggle **Segmentos | Mensagens**; caso contrário só segmentos e badge explícito.

## Ficheiros

| Ficheiro aqui | Destino no projeto Lovable |
|---------------|----------------------------|
| `src/lib/delivery-window.ts` | `src/lib/delivery-window.ts` |
| `src/lib/csv-data-fragment.ts` | fundir com o vosso `csv-data.ts` |
| `src/hooks/use-twilio-data-fragment.ts` | fundir com o vosso hook |
| `supabase/functions/csv-proxy-fragment.ts` | notas para `csv-proxy/index.ts` |
| `src/components/dashboard/DeliveryTab.tsx` | substituir / fundir `DeliveryTab.tsx` |
| `src/pages/Index-fragment.tsx` | passar `deliveryInsightsTimeseries` ao `DeliveryTab` |

Revê imports (`@/`) conforme o alias do teu projeto.
