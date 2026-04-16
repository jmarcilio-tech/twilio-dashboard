/**
 * Fundir em supabase/functions/csv-proxy/index.ts (ou o vosso allowlist).
 *
 * 1) Adicionar à lista de URLs permitidas / paths:
 *    conf_delivery_insights_timeseries.csv
 *
 * 2) No mesmo sítio onde já fazem fetch de outros CSVs do dashboard, incluir:
 */

// const TIMESERIES_PATH = "conf_delivery_insights_timeseries.csv";
// const TIMESERIES_URL = `${RAW_BASE}/${REPO}/${BRANCH}/${TIMESERIES_PATH}`;
// … fetch em paralelo com conf_delivery_horario.csv …
// return JSON body com campo deliveryInsightsTimeseriesText ou parse no cliente.
