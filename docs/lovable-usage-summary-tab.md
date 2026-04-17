# Guia Usage por conta — prompt para Lovable

**Antes de prompts longos:** ver divisão em 3 abas e KPI **gasto total** em [`lovable-dashboard-3-abas.md`](./lovable-dashboard-3-abas.md).

Este documento liga o **pipeline** (`conf_usage_billing_snapshot.csv`) a uma **nova guia** no dashboard (Lovable), com **uma linha por conta** + linha agregada `__ORG_SUM__`.

---

## Dados no GitHub (fonte única)

- **Ficheiros:** `conf_usage_billing_snapshot.csv` (resumo) e `conf_usage_billing_by_category.csv` (detalhe por categoria), branch `master`, repo `jmarcilio-tech/twilio-dashboard`.
- **Raw:** `https://raw.githubusercontent.com/jmarcilio-tech/twilio-dashboard/master/conf_usage_billing_snapshot.csv` · `https://raw.githubusercontent.com/jmarcilio-tech/twilio-dashboard/master/conf_usage_billing_by_category.csv`
- **Workflow:** `usage-billing-snapshot.yml` (gera o CSV com `USAGE_WRITE_CSV=1`).

### Colunas (cabeçalho)

| Coluna | Significado |
|--------|-------------|
| `Conta` | Nome curto: NS, Joao, Bernardo, Rafa, Havenmove, Rehableaf, Richard, Naturemove, ou `__ORG_SUM__` (soma todas as contas) |
| `Range` | Descrição da janela (default **`cover_days`** ~Last 24h vs Insights SMS; legado `rolling_24h_proxy`; ou intervalo `USAGE_START_DATE` / `USAGE_END_DATE` para **Usage Summary** do mês) |
| `TotalPrice_Totalprice` | USD — categoria `totalprice` da API (agregada na janela) |
| `SMS_Count` | Contagem agregada categoria `sms` |
| `SMS_Usage` | Uso agregado categoria `sms` (segmentos/unidade Twilio) |
| `SMS_Price` | USD — preço agregado categoria `sms` |
| `Sum_Price_NoTotalprice` | Soma de `price` de todas as categorias exceto `totalprice` (diagnóstico) |
| `SMS_Subcategories_Sample` | Amostra `categoria:count` das subcategorias `sms-*` |
| `Extraido_Utc` | Momento da extração |

**`conf_usage_billing_by_category.csv`:** `Conta`, `Categoria`, `Count`, `Usage`, `Price_USD`, `Range`, `Extraido_Utc` — ver parser e UI em `docs/lovable-usage-hybrid/`.

**`conf_usage_billing_daily.csv`:** série diária GMT (`Data_Utc`) por conta e categoria (`totalprice`, `sms` por defeito) — ver `usage-billing-daily.ts` e workflow inputs `billing_month` / `usage_start_date`+`usage_end_date`.

**Regra de ouro na UI:** mostrar sempre o texto de **`Range`** junto aos números, para o utilizador saber se está a ver **~Last 24h** ou **mês civil GMT**.

---

## Pipeline — mês alinhado à Usage Summary (opcional)

Para o CSV refletir **2026-04-01 … 2026-04-30** (como na consola Usage com `date=2026-04`), o job GitHub (ou local) pode definir:

```bash
USAGE_START_DATE=2026-04-01
USAGE_END_DATE=2026-04-30
USAGE_WRITE_CSV=1
```

(Isso tem precedência sobre `USAGE_DATE_STRATEGY` / `USAGE_UTC_DAY`.) O script agrega **todas** as linhas `Usage/Records` por categoria nesse intervalo.

---

## Prompt (copiar para a Lovable)

```
Cria uma nova guia no dashboard: "Usage" (ou "Billing / Usage"), para comparar com Twilio Console → Billing → Usage summary.

Dados:
- Ler `conf_usage_billing_snapshot.csv` do GitHub raw (mesmo padrão dos outros CSVs: proxy Supabase ou URL configurada).
- Uma linha por conta: NS, Joao, Bernardo, Rafa, Havenmove, Rehableaf, Richard, Naturemove.
- Linha especial Conta === "__ORG_SUM__" → mostrar como "Todas as contas (soma)" no rodapé ou cartão separado; não misturar com o seletor por conta.

UI:
- Secletor ou tabs por `Conta` (excluir __ORG_SUM__ da lista de contas individuais).
- Para a conta selecionada, cartões principais:
  - Total (USD): TotalPrice_Totalprice
  - SMS — preço (USD): SMS_Price
  - SMS — transações: SMS_Count e SMS_Usage (mostrar os dois com legenda: count vs usage, conforme Twilio)
- Bloco de texto secundário: Sum_Price_NoTotalprice e SMS_Subcategories_Sample (formato legível).
- Sempre mostrar `Range` e `Extraido_Utc` visíveis (subtitle ou info) — são a "fonte da verdade" da janela temporal.
- Banner ou callout visível no topo da guia: os valores são o instante da extração; se a consola Twilio foi consultada depois, contagens/preços podem ser superiores na consola (~alguns % em contas com volume) — não "corrigir" números no frontend sem nova fonte (seria inventar dados). Opções reais: aguardar próximo job, mostrar `Extraido_Utc`, ou disparar manualmente o workflow no GitHub.

Comportamento:
- Não chamar a API Twilio no browser; só CSV.
- Estados: loading, erro de rede, CSV vazio.
- Estilo consistente com o resto do dashboard (cards, tipografia).

Opcional (se já existir filtro global de mês no app):
- Documentar que o pipeline pode ser corrido com USAGE_START_DATE + USAGE_END_DATE para gerar o CSV desse mês; a UI só precisa de recarregar o CSV.
```

---

## Critérios de aceite

- [ ] Todas as contas do CSV aparecem no seletor (8 contas).
- [ ] `__ORG_SUM__` aparece como agregado global, não como "conta".
- [ ] Valores batem com o CSV; comparação com a consola Twilio só é válida para o mesmo intervalo (`Range`) e **depois** de confirmar que o `Extraido_Utc` do CSV não é anterior ao momento da captura na consola (senão diferenças de volume são esperadas).
- [ ] `Range` e aviso temporal (`Extraido_Utc` / fonte GitHub) sempre visíveis.
