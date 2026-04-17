# Pipeline — estado do projeto (checklist)

Documento para **apresentação e acompanhamento**: cada linha é uma tarefa; **`[x]`** = concluída, **`[ ]`** = pendente.

**Como usar:** ao apresentar, percorre as secções; no dia a dia, atualiza as caixas no editor (Markdown). Em Issues/PRs do GitHub as caixas também podem ser clicáveis.

**Relacionado:** [Documentação detalhada do pipeline](./pipeline-documentacao.md) · [Lovable — 3 abas isoladas](./lovable-dashboard-3-abas.md)

---

## 1. Backend — repositório `twilio-dash`

- [x] Script `scripts/fetch_delivery_insights_timeseries.py` (slots 15 min UTC, Insight 5, escrita opcional do CSV)
- [x] Workflow `.github/workflows/delivery-insights-timeseries.yml` (schedule + `workflow_dispatch`, artefacto + commit do CSV)
- [x] Documentação em `docs/pipeline-documentacao.md` (CSV timeseries + workflow + regra UI “não fingir mensagens sem timeseries”)
- [x] Pasta de referência Lovable `docs/lovable-delivery-sync/` (`delivery-window.ts`, `DeliveryTab.tsx`, fragmentos, `README.md`)
- [x] Commit e push das alterações acima para `origin/master` (repo remoto configurado)
- [ ] `conf_delivery_insights_timeseries.csv` presente no `master` após run bem-sucedido do workflow (verificar no GitHub / raw URL)
- [ ] Workflow **Delivery — Insights timeseries** a correr sem erros e tempo aceitável (ajustar `DELIVERY_INSIGHTS_TS_*` se necessário)

---

## 2. GitHub Actions — operação

- [x] Disparo manual (`workflow_dispatch`) do workflow **Delivery — Insights timeseries (15 min)** pelo menos uma vez
- [ ] Confirmar no log do job que o passo **Insights timeseries → CSV** conclui e que o job **commitar-timeseries** fez push do CSV (quando há linhas)

---

## 3. Frontend — Lovable / app React

- [x] Comportamento geral da aba Delivery aprovado (janela do gráfico alinhada com totais / legenda)
- [ ] Integrar `src/lib/delivery-window.ts` (ou equivalente) a partir de `docs/lovable-delivery-sync/`
- [ ] Atualizar `DeliveryTab.tsx`: legenda + total da janela; remover `past4hTotals` da evolução; labels “segmentos / janela selecionada”
- [ ] `supabase/functions/csv-proxy`: permitir e servir `conf_delivery_insights_timeseries.csv`
- [ ] `src/lib/csv-data.ts`: tipos + parser robusto (ex. Papa.parse se houver aspas nos CSVs)
- [ ] `use-twilio-data.ts` + `Index.tsx`: expor e passar `deliveryInsightsTimeseries` ao `DeliveryTab`
- [ ] Toggle **Segmentos | Mensagens** só quando existir dataset timeseries; badge/tooltip da unidade
- [ ] Corrigir ou remover aviso incorreto de **“conta truncada”** / truncagem (só mostrar com critério real, ex. `Api_Pages_Capped`, ou só tooltip no nome)

---

## 4. Verificação final (QA)

- [ ] Mudar 5m / 15m / 1h / 4h / hoje / ontem: números laterais e **Total** do header acompanham a janela
- [ ] Sem valores “congelados” do `conf_delivery_insights_4h.csv` na secção evolução
- [ ] Raw CSV acessível pelo dashboard (CORS/proxy) — ex.: `https://raw.githubusercontent.com/jmarcilio-tech/twilio-dashboard/master/conf_delivery_insights_timeseries.csv`

---

*Checklist alinhado ao estado do repo e às tarefas típicas no cliente; atualizar conforme o projeto avança.*
