/**
 * Parser para conf_usage_billing_daily.csv
 * Colunas: Conta, Data_Utc, Categoria, Count, Usage, Price_USD, Range, Extraido_Utc
 */

export type UsageBillingDailyRow = {
  Conta: string;
  Data_Utc: string;
  Categoria: string;
  Count: number;
  Usage: number;
  priceUsd: number;
  Range: string;
  Extraido_Utc: string;
};

function num(s: string | undefined): number {
  const n = Number(String(s ?? "").replace(",", ".").trim());
  return Number.isFinite(n) ? n : 0;
}

export function parseUsageBillingDailyCsv(text: string): UsageBillingDailyRow[] {
  const lines = text.trim().split(/\r?\n/);
  if (lines.length < 2) return [];
  const header = lines[0].split(",").map((h) => h.trim());
  const ix = (name: string) => header.indexOf(name);
  if (ix("Conta") < 0 || ix("Data_Utc") < 0) return [];

  const out: UsageBillingDailyRow[] = [];
  for (let i = 1; i < lines.length; i++) {
    const cols = lines[i].split(",");
    if (cols.length < header.length) continue;
    const g = (n: string) => cols[ix(n)]?.trim() ?? "";
    out.push({
      Conta: g("Conta"),
      Data_Utc: g("Data_Utc"),
      Categoria: g("Categoria"),
      Count: Math.round(num(g("Count"))),
      Usage: num(g("Usage")),
      priceUsd: num(g("Price_USD")),
      Range: g("Range"),
      Extraido_Utc: g("Extraido_Utc"),
    });
  }
  return out;
}

/** Agrega por dia (ex.: total `totalprice` + `sms` usage) para um gráfico. */
export function pivotDailySpendSms(rows: UsageBillingDailyRow[], account: string) {
  const byDay = new Map<string, { priceTotal: number; smsUsage: number; smsCount: number }>();
  for (const r of rows) {
    if (r.Conta !== account) continue;
    if (!byDay.has(r.Data_Utc)) {
      byDay.set(r.Data_Utc, { priceTotal: 0, smsUsage: 0, smsCount: 0 });
    }
    const b = byDay.get(r.Data_Utc)!;
    if (r.Categoria === "totalprice") {
      b.priceTotal += r.priceUsd;
    }
    if (r.Categoria === "sms") {
      b.smsUsage += r.Usage;
      b.smsCount += r.Count;
    }
  }
  return [...byDay.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, v]) => ({ date, ...v }));
}
