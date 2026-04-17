/**
 * Parser + hierarquia para conf_usage_billing_by_category.csv
 * Colunas: Conta, Categoria, Count, Usage, Price_USD, Range, Extraido_Utc
 *
 * Preferir Papa.parse se o CSV tiver campos entre aspas.
 */

export type UsageByCategoryRow = {
  Conta: string;
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

/** Parser mínimo (CSV simples). */
export function parseUsageBillingByCategoryCsv(text: string): UsageByCategoryRow[] {
  const lines = text.trim().split(/\r?\n/);
  if (lines.length < 2) return [];
  const header = lines[0].split(",").map((h) => h.trim());
  const ix = (name: string) => header.indexOf(name);
  if (ix("Conta") < 0 || ix("Categoria") < 0) return [];

  const out: UsageByCategoryRow[] = [];
  for (let i = 1; i < lines.length; i++) {
    const cols = lines[i].split(",");
    if (cols.length < header.length) continue;
    const g = (n: string) => cols[ix(n)]?.trim() ?? "";
    out.push({
      Conta: g("Conta"),
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

/** Pai imediato = prefixo mais longo presente no conjunto (ex.: sms-outbound para sms-outbound-tollfree). */
export function findParentCategory(category: string, allCategories: Set<string>): string | null {
  let best: string | null = null;
  let bestLen = -1;
  for (const c of allCategories) {
    if (!c || c === category) continue;
    if (category === c || !category.startsWith(c + "-")) continue;
    if (c.length > bestLen) {
      best = c;
      bestLen = c.length;
    }
  }
  return best;
}

export type UsageCategoryNode = {
  id: string;
  row: UsageByCategoryRow | null;
  children: UsageCategoryNode[];
};

/**
 * Árvore por conta: cada categoria do CSV é um nó; pai = maior prefixo `pai-`
 * presente no conjunto (ex.: sms → sms-outbound → sms-outbound-tollfree).
 */
export function buildUsageCategoryTree(rows: UsageByCategoryRow[], account: string): UsageCategoryNode[] {
  const filtered = rows.filter((r) => r.Conta === account && r.Categoria);
  if (filtered.length === 0) return [];
  const all = new Set(filtered.map((r) => r.Categoria));
  const byCat = new Map<string, UsageByCategoryRow>();
  filtered.forEach((r) => byCat.set(r.Categoria, r));

  const nodes = new Map<string, UsageCategoryNode>();
  for (const cat of all) {
    nodes.set(cat, { id: cat, row: byCat.get(cat) ?? null, children: [] });
  }
  const roots: UsageCategoryNode[] = [];
  for (const cat of all) {
    const p = findParentCategory(cat, all);
    const node = nodes.get(cat)!;
    if (p && nodes.has(p)) {
      nodes.get(p)!.children.push(node);
    } else {
      roots.push(node);
    }
  }
  const price = (n: UsageCategoryNode) => n.row?.priceUsd ?? 0;
  const sortRec = (arr: UsageCategoryNode[]) => {
    arr.sort((a, b) => price(b) - price(a) || a.id.localeCompare(b.id));
    arr.forEach((n) => sortRec(n.children));
  };
  sortRec(roots);
  return roots;
}
