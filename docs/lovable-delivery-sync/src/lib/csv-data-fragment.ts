/**
 * Fundir no vosso src/lib/csv-data.ts (ou equivalente).
 * Inclui tipos + parser para conf_delivery_insights_timeseries.csv.
 */

import type { DeliveryInsightsTimeseriesRow } from "./delivery-window";

export const DELIVERY_INSIGHTS_TIMESERIES_COLUMNS = [
  "Conta",
  "Categoria",
  "Direcao",
  "Slot_15min",
  "Insight_Delivered_Msgs",
  "Insight_Failed_Msgs",
  "Insight_Undelivered_Msgs",
  "Insight_Sent_Msgs",
  "Insight_Delivery_Unknown_Msgs",
  "Insight_Total_Msgs",
  "Extraido_Utc",
] as const;

function num(v: string | undefined): number {
  const n = Number(String(v ?? "").replace(",", ".").trim());
  return Number.isFinite(n) ? n : 0;
}

export function parseDeliveryInsightsTimeseriesCsv(text: string): DeliveryInsightsTimeseriesRow[] {
  const lines = text.trim().split(/\r?\n/);
  if (lines.length < 2) return [];
  const header = lines[0].split(",").map((h) => h.trim());
  const idx = (name: string) => header.indexOf(name);

  const out: DeliveryInsightsTimeseriesRow[] = [];
  for (let i = 1; i < lines.length; i++) {
    const cols = lines[i].split(",");
    if (cols.length < header.length) continue;
    const get = (name: string) => cols[idx(name)]?.trim() ?? "";
    out.push({
      Conta: get("Conta"),
      Categoria: get("Categoria"),
      Direcao: get("Direcao"),
      Slot_15min: get("Slot_15min"),
      Insight_Delivered_Msgs: num(get("Insight_Delivered_Msgs")),
      Insight_Failed_Msgs: num(get("Insight_Failed_Msgs")),
      Insight_Undelivered_Msgs: num(get("Insight_Undelivered_Msgs")),
      Insight_Sent_Msgs: num(get("Insight_Sent_Msgs")),
      Insight_Delivery_Unknown_Msgs: num(get("Insight_Delivery_Unknown_Msgs")),
      Insight_Total_Msgs: num(get("Insight_Total_Msgs")),
      Extraido_Utc: get("Extraido_Utc") || undefined,
    });
  }
  return out;
}

/** Nota: CSVs com campos entre aspas e vírgulas internas precisam de parser robusto (ex. Papa.parse). */
