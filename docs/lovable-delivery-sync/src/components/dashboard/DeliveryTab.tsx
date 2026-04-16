/**
 * Referência para o projeto Lovable: copiar para src/components/dashboard/DeliveryTab.tsx
 * e ajustar imports (@/), UI (Card, Badge, Tooltip) e tipos partilhados.
 *
 * Requisitos: react, recharts, e o módulo @/lib/delivery-window (nesta pasta de sync).
 *
 * Comportamento:
 * - Legenda lateral + Total do header = chartTotals / chartGrandTotal na janela selecionada.
 * - Segmentos: conf_delivery_horario.csv (slots 15 min UTC).
 * - Mensagens: só se deliveryInsightsTimeseries tiver linhas (conf_delivery_insights_timeseries.csv).
 * - Não usar conf_delivery_insights_4h.csv para estes totais.
 */

import { useMemo, useState, useEffect } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  type ChartWindow,
  type DeliveryHorarioRow,
  type DeliveryInsightsTimeseriesRow,
  type HorarioSegmentKey,
  type InsightMsgKey,
  HORARIO_SEGMENT_COLS,
  PRIMARY_SEGMENT,
  SECONDARY_SEGMENT,
  PRIMARY_MSG_LABELS,
  SECONDARY_MSG_LABELS,
  chartWindowBoundsUtc,
  filterHorarioByWindow,
  filterTimeseriesByWindow,
  aggregateHorarioSegments,
  aggregateTimeseriesMessages,
  parseSlot15StartUtc,
} from "@/lib/delivery-window";

const WINDOW_OPTIONS: { value: ChartWindow; label: string }[] = [
  { value: "5m", label: "5 min" },
  { value: "15m", label: "15 min" },
  { value: "1h", label: "1 h" },
  { value: "4h", label: "4 h" },
  { value: "today", label: "Hoje (UTC)" },
  { value: "yesterday", label: "Ontem (UTC)" },
];

const SEG_COLORS: Partial<Record<HorarioSegmentKey, string>> = {
  Delivered: "#22c55e",
  Failed: "#ef4444",
  Undelivered: "#f97316",
  Sent: "#3b82f6",
  Sending: "#a855f7",
  Delivery_Unknown: "#64748b",
  Accepted: "#06b6d4",
  Queued: "#eab308",
};

const MSG_COLORS: Partial<Record<InsightMsgKey, string>> = {
  Insight_Delivered_Msgs: "#22c55e",
  Insight_Failed_Msgs: "#ef4444",
  Insight_Undelivered_Msgs: "#f97316",
  Insight_Sent_Msgs: "#3b82f6",
  Insight_Delivery_Unknown_Msgs: "#64748b",
};

export interface DeliveryTabProps {
  deliveryHorario: DeliveryHorarioRow[];
  /** Opcional: se vazio / omitido, só modo Segmentos. */
  deliveryInsightsTimeseries?: DeliveryInsightsTimeseriesRow[];
  selectedAccount?: string | null;
}

type UnitMode = "segments" | "messages";

function buildLineDataSegments(rows: DeliveryHorarioRow[]) {
  const map = new Map<string, Record<HorarioSegmentKey, number>>();
  for (const r of rows) {
    const k = r.Slot_15min;
    if (!map.has(k)) {
      const o = Object.fromEntries(HORARIO_SEGMENT_COLS.map((c) => [c, 0])) as Record<HorarioSegmentKey, number>;
      map.set(k, o);
    }
    const b = map.get(k)!;
    for (const c of HORARIO_SEGMENT_COLS) {
      b[c] += Number(r[c]) || 0;
    }
  }
  return [...map.entries()]
    .sort((a, b) => (parseSlot15StartUtc(a[0])?.getTime() ?? 0) - (parseSlot15StartUtc(b[0])?.getTime() ?? 0))
    .map(([slot, vals]) => ({ slot, ...vals }));
}

function buildLineDataMessages(rows: DeliveryInsightsTimeseriesRow[]) {
  const keys: InsightMsgKey[] = [
    "Insight_Delivered_Msgs",
    "Insight_Failed_Msgs",
    "Insight_Undelivered_Msgs",
    "Insight_Sent_Msgs",
    "Insight_Delivery_Unknown_Msgs",
  ];
  const map = new Map<string, Record<InsightMsgKey, number>>();
  for (const r of rows) {
    const k = r.Slot_15min;
    if (!map.has(k)) {
      const o = Object.fromEntries(keys.map((x) => [x, 0])) as Record<InsightMsgKey, number>;
      map.set(k, o);
    }
    const b = map.get(k)!;
    for (const x of keys) {
      b[x] += Number(r[x]) || 0;
    }
  }
  return [...map.entries()]
    .sort((a, b) => (parseSlot15StartUtc(a[0])?.getTime() ?? 0) - (parseSlot15StartUtc(b[0])?.getTime() ?? 0))
    .map(([slot, vals]) => ({ slot, ...vals }));
}

export function DeliveryTab({
  deliveryHorario,
  deliveryInsightsTimeseries = [],
  selectedAccount = null,
}: DeliveryTabProps) {
  const [chartWindow, setChartWindow] = useState<ChartWindow>("4h");
  const hasTimeseries = deliveryInsightsTimeseries.length > 0;
  const [unitMode, setUnitMode] = useState<UnitMode>("segments");

  useEffect(() => {
    if (!hasTimeseries && unitMode === "messages") {
      setUnitMode("segments");
    }
  }, [hasTimeseries, unitMode]);

  const nowUtc = useMemo(() => new Date(), []);
  const { start, end } = useMemo(
    () => chartWindowBoundsUtc(chartWindow, nowUtc),
    [chartWindow, nowUtc],
  );

  const filteredHorario = useMemo(
    () => filterHorarioByWindow(deliveryHorario, start, end, selectedAccount),
    [deliveryHorario, start, end, selectedAccount],
  );
  const filteredTs = useMemo(
    () =>
      hasTimeseries
        ? filterTimeseriesByWindow(deliveryInsightsTimeseries, start, end, selectedAccount)
        : [],
    [hasTimeseries, deliveryInsightsTimeseries, start, end, selectedAccount],
  );

  const activeUnit: UnitMode = hasTimeseries && unitMode === "messages" ? "messages" : "segments";

  const { chartTotals, chartGrandTotal } = useMemo(() => {
    if (activeUnit === "messages") {
      return aggregateTimeseriesMessages(filteredTs);
    }
    return aggregateHorarioSegments(filteredHorario);
  }, [activeUnit, filteredHorario, filteredTs]);

  const lineData = useMemo(() => {
    if (activeUnit === "messages") {
      return buildLineDataMessages(filteredTs);
    }
    return buildLineDataSegments(filteredHorario);
  }, [activeUnit, filteredHorario, filteredTs]);

  const stackKeys: string[] =
    activeUnit === "messages"
      ? [
          "Insight_Delivered_Msgs",
          "Insight_Failed_Msgs",
          "Insight_Undelivered_Msgs",
          "Insight_Sent_Msgs",
          "Insight_Delivery_Unknown_Msgs",
        ]
      : [...HORARIO_SEGMENT_COLS];

  const unitTitle = activeUnit === "messages" ? "Mensagens" : "Segmentos";
  const unitDetail =
    activeUnit === "messages"
      ? "Mensagens por slot (Insight 5), agregadas na janela selecionada. Fonte: conf_delivery_insights_timeseries.csv · UTC 15 min."
      : "Segmentos por slot, agregados na janela selecionada. Fonte: conf_delivery_horario.csv · UTC 15 min.";

  return (
    <section className="space-y-4 rounded-lg border border-border bg-card p-4 text-card-foreground">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-lg font-semibold">Evolução de Delivery</h2>
            <span
              className="inline-flex cursor-help rounded-md border border-border bg-muted px-2 py-0.5 text-xs font-medium"
              title={unitDetail}
            >
              {unitTitle}
            </span>
          </div>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{unitDetail}</p>
        </div>
        <div className="text-right">
          <div className="text-xs uppercase tracking-wide text-muted-foreground">Total (janela)</div>
          <div className="text-2xl font-bold tabular-nums" title={unitDetail}>
            {chartGrandTotal.toLocaleString()}
          </div>
        </div>
      </header>

      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-muted-foreground">Janela do gráfico:</span>
        {WINDOW_OPTIONS.map((w) => (
          <button
            key={w.value}
            type="button"
            className={`rounded-md border px-2 py-1 text-xs ${
              chartWindow === w.value ? "border-primary bg-primary/10 font-medium" : "border-border bg-background"
            }`}
            onClick={() => setChartWindow(w.value)}
          >
            {w.label}
          </button>
        ))}
      </div>

      {hasTimeseries ? (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted-foreground">Unidade:</span>
          <button
            type="button"
            className={`rounded-md border px-2 py-1 text-xs ${unitMode === "segments" ? "border-primary bg-primary/10 font-medium" : "border-border"}`}
            onClick={() => setUnitMode("segments")}
          >
            Segmentos
          </button>
          <button
            type="button"
            className={`rounded-md border px-2 py-1 text-xs ${unitMode === "messages" ? "border-primary bg-primary/10 font-medium" : "border-border"}`}
            onClick={() => setUnitMode("messages")}
          >
            Mensagens
          </button>
        </div>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_220px]">
        <div className="min-h-[280px] w-full">
          <ResponsiveContainer width="100%" height={320}>
            <AreaChart data={lineData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
              <XAxis dataKey="slot" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
              <YAxis tick={{ fontSize: 10 }} width={48} />
              <Tooltip
                contentStyle={{ fontSize: 12 }}
                labelFormatter={(slot) => `Slot UTC: ${slot}`}
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              {stackKeys.map((key) => (
                <Area
                  key={key}
                  type="monotone"
                  dataKey={key}
                  stackId="a"
                  stroke={activeUnit === "messages" ? MSG_COLORS[key as InsightMsgKey] : SEG_COLORS[key as HorarioSegmentKey]}
                  fill={activeUnit === "messages" ? MSG_COLORS[key as InsightMsgKey] : SEG_COLORS[key as HorarioSegmentKey]}
                  fillOpacity={0.85}
                  name={key}
                />
              ))}
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <aside className="space-y-4 text-sm">
          <div>
            <div className="mb-1 text-xs font-semibold uppercase text-muted-foreground">Principais</div>
            <ul className="space-y-1">
              {activeUnit === "segments"
                ? PRIMARY_SEGMENT.map((k) => (
                    <li key={k} className="flex justify-between gap-2">
                      <span className="flex items-center gap-2">
                        <span className="h-2 w-2 rounded-sm" style={{ background: SEG_COLORS[k] }} />
                        {k}
                      </span>
                      <span className="tabular-nums font-medium">{(chartTotals as Record<string, number>)[k]?.toLocaleString() ?? 0}</span>
                    </li>
                  ))
                : PRIMARY_MSG_LABELS.map(({ key, label }) => (
                    <li key={key} className="flex justify-between gap-2">
                      <span className="flex items-center gap-2">
                        <span className="h-2 w-2 rounded-sm" style={{ background: MSG_COLORS[key] }} />
                        {label}
                      </span>
                      <span className="tabular-nums font-medium">{(chartTotals as Record<string, number>)[key]?.toLocaleString() ?? 0}</span>
                    </li>
                  ))}
            </ul>
          </div>
          <div>
            <div className="mb-1 text-xs font-semibold uppercase text-muted-foreground">Outros</div>
            <ul className="space-y-1">
              {activeUnit === "segments"
                ? SECONDARY_SEGMENT.map((k) => (
                    <li key={k} className="flex justify-between gap-2">
                      <span className="flex items-center gap-2">
                        <span className="h-2 w-2 rounded-sm" style={{ background: SEG_COLORS[k] }} />
                        {k}
                      </span>
                      <span className="tabular-nums font-medium">{(chartTotals as Record<string, number>)[k]?.toLocaleString() ?? 0}</span>
                    </li>
                  ))
                : SECONDARY_MSG_LABELS.map(({ key, label }) => (
                    <li key={key} className="flex justify-between gap-2">
                      <span className="flex items-center gap-2">
                        <span className="h-2 w-2 rounded-sm" style={{ background: MSG_COLORS[key] }} />
                        {label}
                      </span>
                      <span className="tabular-nums font-medium">{(chartTotals as Record<string, number>)[key]?.toLocaleString() ?? 0}</span>
                    </li>
                  ))}
            </ul>
          </div>
        </aside>
      </div>
    </section>
  );
}
