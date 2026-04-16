/**
 * Janelas do gráfico Delivery e agregação por Slot_15min (UTC),
 * alinhado a conf_delivery_horario.csv e conf_delivery_insights_timeseries.csv.
 */

export type ChartWindow = "5m" | "15m" | "1h" | "4h" | "today" | "yesterday";

/** Colunas de segmentos em conf_delivery_horario.csv (após Slot_15min, Conta, Categoria). */
export const HORARIO_SEGMENT_COLS = [
  "Delivered",
  "Failed",
  "Undelivered",
  "Sent",
  "Sending",
  "Delivery_Unknown",
  "Accepted",
  "Queued",
] as const;

export type HorarioSegmentKey = (typeof HORARIO_SEGMENT_COLS)[number];

/** Estados “Insight 5” no timeseries de mensagens (script Python). */
export const INSIGHT_MSG_KEYS = [
  "Insight_Delivered_Msgs",
  "Insight_Failed_Msgs",
  "Insight_Undelivered_Msgs",
  "Insight_Sent_Msgs",
  "Insight_Delivery_Unknown_Msgs",
] as const;

export type InsightMsgKey = (typeof INSIGHT_MSG_KEYS)[number];

export const PRIMARY_SEGMENT: readonly HorarioSegmentKey[] = [
  "Delivered",
  "Failed",
  "Undelivered",
  "Sent",
];

export const SECONDARY_SEGMENT: readonly HorarioSegmentKey[] = [
  "Sending",
  "Delivery_Unknown",
  "Accepted",
  "Queued",
];

/** Legenda em modo mensagens (totais por janela). */
export const PRIMARY_MSG_LABELS: { key: InsightMsgKey; label: string }[] = [
  { key: "Insight_Delivered_Msgs", label: "Delivered" },
  { key: "Insight_Failed_Msgs", label: "Failed" },
  { key: "Insight_Undelivered_Msgs", label: "Undelivered" },
  { key: "Insight_Sent_Msgs", label: "Sent" },
];

export const SECONDARY_MSG_LABELS: { key: InsightMsgKey; label: string }[] = [
  { key: "Insight_Delivery_Unknown_Msgs", label: "Delivery unknown" },
];

function startOfUtcDay(d: Date): Date {
  return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate(), 0, 0, 0, 0));
}

function addUtcDays(d: Date, days: number): Date {
  return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() + days, 0, 0, 0, 0));
}

/**
 * Início (inclusivo) e fim (exclusivo) da janela em UTC, alinhado ao preset do gráfico.
 */
export function chartWindowBoundsUtc(window: ChartWindow, nowUtc: Date): { start: Date; end: Date } {
  const end = new Date(nowUtc.getTime());
  let start: Date;
  switch (window) {
    case "5m":
      start = new Date(end.getTime() - 5 * 60 * 1000);
      break;
    case "15m":
      start = new Date(end.getTime() - 15 * 60 * 1000);
      break;
    case "1h":
      start = new Date(end.getTime() - 60 * 60 * 1000);
      break;
    case "4h":
      start = new Date(end.getTime() - 4 * 60 * 60 * 1000);
      break;
    case "today": {
      start = startOfUtcDay(end);
      break;
    }
    case "yesterday": {
      const y = addUtcDays(startOfUtcDay(end), -1);
      start = y;
      return { start, end: addUtcDays(y, 1) };
    }
    default:
      start = new Date(end.getTime() - 4 * 60 * 60 * 1000);
  }
  return { start, end };
}

/**
 * Parse Slot_15min como início do slot em UTC ("YYYY-MM-DD HH:MM").
 */
export function parseSlot15StartUtc(slot: string): Date | null {
  const m = String(slot || "").trim().match(/^(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2})/);
  if (!m) return null;
  const y = +m[1];
  const mo = +m[2] - 1;
  const da = +m[3];
  const h = +m[4];
  const mi = +m[5];
  return new Date(Date.UTC(y, mo, da, h, mi, 0, 0));
}

const SLOT_MS = 15 * 60 * 1000;

/** Slot [slotStart, slotStart+15m) intersecta [start, end). */
export function slotIntersectsWindow(slotStart: Date, start: Date, end: Date): boolean {
  const slotEnd = new Date(slotStart.getTime() + SLOT_MS);
  return slotStart < end && slotEnd > start;
}

export interface DeliveryHorarioRow {
  Slot_15min: string;
  Conta: string;
  Categoria: string;
  Delivered: number;
  Failed: number;
  Undelivered: number;
  Sent: number;
  Sending: number;
  Delivery_Unknown: number;
  Accepted: number;
  Queued: number;
  Total_Slot?: number;
}

export interface DeliveryInsightsTimeseriesRow {
  Conta: string;
  Categoria: string;
  Direcao: string;
  Slot_15min: string;
  Insight_Delivered_Msgs: number;
  Insight_Failed_Msgs: number;
  Insight_Undelivered_Msgs: number;
  Insight_Sent_Msgs: number;
  Insight_Delivery_Unknown_Msgs: number;
  Insight_Total_Msgs: number;
  Extraido_Utc?: string;
}

export function filterHorarioByWindow(
  rows: DeliveryHorarioRow[],
  start: Date,
  end: Date,
  conta?: string | null,
): DeliveryHorarioRow[] {
  return rows.filter((r) => {
    if (conta && r.Conta !== conta) return false;
    const s = parseSlot15StartUtc(r.Slot_15min);
    if (!s) return false;
    return slotIntersectsWindow(s, start, end);
  });
}

export function filterTimeseriesByWindow(
  rows: DeliveryInsightsTimeseriesRow[],
  start: Date,
  end: Date,
  conta?: string | null,
): DeliveryInsightsTimeseriesRow[] {
  return rows.filter((r) => {
    if (conta && r.Conta !== conta) return false;
    const s = parseSlot15StartUtc(r.Slot_15min);
    if (!s) return false;
    return slotIntersectsWindow(s, start, end);
  });
}

export function aggregateHorarioSegments(rows: DeliveryHorarioRow[]): {
  chartTotals: Record<HorarioSegmentKey, number>;
  chartGrandTotal: number;
} {
  const chartTotals = Object.fromEntries(HORARIO_SEGMENT_COLS.map((k) => [k, 0])) as Record<
    HorarioSegmentKey,
    number
  >;
  let chartGrandTotal = 0;
  for (const r of rows) {
    for (const k of HORARIO_SEGMENT_COLS) {
      const v = Number(r[k]) || 0;
      chartTotals[k] += v;
    }
    if (r.Total_Slot != null && !Number.isNaN(Number(r.Total_Slot))) {
      chartGrandTotal += Number(r.Total_Slot);
    } else {
      chartGrandTotal += HORARIO_SEGMENT_COLS.reduce((acc, k) => acc + (Number(r[k]) || 0), 0);
    }
  }
  return { chartTotals, chartGrandTotal };
}

export function aggregateTimeseriesMessages(rows: DeliveryInsightsTimeseriesRow[]): {
  chartTotals: Record<InsightMsgKey, number>;
  chartGrandTotal: number;
} {
  const chartTotals = Object.fromEntries(INSIGHT_MSG_KEYS.map((k) => [k, 0])) as Record<InsightMsgKey, number>;
  let chartGrandTotal = 0;
  for (const r of rows) {
    for (const k of INSIGHT_MSG_KEYS) {
      chartTotals[k] += Number(r[k]) || 0;
    }
    chartGrandTotal += Number(r.Insight_Total_Msgs) || 0;
  }
  return { chartTotals, chartGrandTotal };
}
