/**
 * Referência: guia Usage híbrida (snapshot + por categoria).
 * Fundir com o projeto Lovable (imports @/, Card, Alert, Select, Table).
 */

import { useMemo, useState } from "react";
import {
  parseUsageBillingByCategoryCsv,
  buildUsageCategoryTree,
  type UsageByCategoryRow,
  type UsageCategoryNode,
} from "@/lib/usage-billing-by-category";

/** Linha do conf_usage_billing_snapshot.csv (já parseada). */
export type UsageSnapshotRow = {
  Conta: string;
  Range: string;
  TotalPrice_Totalprice: number;
  SMS_Count: number;
  SMS_Usage: number;
  SMS_Price: number;
  Sum_Price_NoTotalprice: number;
  SMS_Subcategories_Sample: string;
  Extraido_Utc: string;
};

export interface UsageBillingTabProps {
  snapshotRows: UsageSnapshotRow[];
  /** Texto CSV ou null se fetch falhou. */
  byCategoryCsvText: string | null;
  /** true se 404 / ficheiro ainda não existe no repo. */
  byCategoryMissing?: boolean;
}

function CategoryRows({ nodes, depth = 0 }: { nodes: UsageCategoryNode[]; depth?: number }) {
  return (
    <>
      {nodes.map((n) => (
        <div key={n.id} className="min-w-0">
          <details className="group border-b border-border" open={depth < 1}>
            <summary
              className="flex cursor-pointer list-none items-center gap-2 py-2 pl-2 hover:bg-muted/50"
              style={{ paddingLeft: depth * 12 + 8 }}
            >
              <span className="text-muted-foreground group-open:rotate-90">▸</span>
              <span className="font-mono text-sm">{n.id}</span>
              {n.row && (
                <span className="ml-auto flex gap-4 text-right text-xs tabular-nums text-muted-foreground">
                  <span>{n.row.Count}</span>
                  <span>{n.row.Usage}</span>
                  <span className="text-foreground">{n.row.priceUsd.toFixed(4)} USD</span>
                </span>
              )}
            </summary>
            {n.children.length > 0 && (
              <div className="pb-1">
                <CategoryRows nodes={n.children} depth={depth + 1} />
              </div>
            )}
          </details>
        </div>
      ))}
    </>
  );
}

export function UsageBillingTab({ snapshotRows, byCategoryCsvText, byCategoryMissing }: UsageBillingTabProps) {
  const accounts = useMemo(
    () => snapshotRows.map((r) => r.Conta).filter((c) => c && c !== "__ORG_SUM__"),
    [snapshotRows],
  );
  const orgRow = useMemo(() => snapshotRows.find((r) => r.Conta === "__ORG_SUM__"), [snapshotRows]);
  const [account, setAccount] = useState(accounts[0] ?? "");

  const byCategoryRows: UsageByCategoryRow[] = useMemo(() => {
    if (!byCategoryCsvText?.trim()) return [];
    return parseUsageBillingByCategoryCsv(byCategoryCsvText);
  }, [byCategoryCsvText]);

  const tree = useMemo(() => buildUsageCategoryTree(byCategoryRows, account), [byCategoryRows, account]);
  const snap = snapshotRows.find((r) => r.Conta === account);

  const showTable = byCategoryRows.length > 0 && byCategoryRows.some((r) => r.Conta === account);

  return (
    <div className="space-y-6 p-4">
      <header>
        <h1 className="text-xl font-semibold">Usage / Billing</h1>
        <p className="text-sm text-muted-foreground">Comparar com Twilio Console → Billing → Usage summary</p>
      </header>

      <div className="flex flex-wrap items-center gap-3">
        <label className="text-sm text-muted-foreground">Conta</label>
        <select
          className="rounded-md border border-input bg-background px-3 py-2 text-sm"
          value={account}
          onChange={(e) => setAccount(e.target.value)}
        >
          {accounts.map((a) => (
            <option key={a} value={a}>
              {a}
            </option>
          ))}
        </select>
      </div>

      {snap && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-lg border border-border p-4">
            <div className="text-xs text-muted-foreground">Total (USD)</div>
            <div className="text-2xl font-semibold tabular-nums">{snap.TotalPrice_Totalprice.toFixed(2)}</div>
          </div>
          <div className="rounded-lg border border-border p-4">
            <div className="text-xs text-muted-foreground">SMS — preço (USD)</div>
            <div className="text-2xl font-semibold tabular-nums">{snap.SMS_Price.toFixed(2)}</div>
          </div>
          <div className="rounded-lg border border-border p-4">
            <div className="text-xs text-muted-foreground">SMS — count</div>
            <div className="text-2xl font-semibold tabular-nums">{snap.SMS_Count}</div>
          </div>
          <div className="rounded-lg border border-border p-4">
            <div className="text-xs text-muted-foreground">SMS — usage</div>
            <div className="text-2xl font-semibold tabular-nums">{snap.SMS_Usage}</div>
          </div>
        </div>
      )}

      <div className="rounded-lg border border-border bg-muted/30 p-3 text-xs text-muted-foreground">
        <div>
          <span className="font-medium text-foreground">Range:</span> {snap?.Range ?? "—"}
        </div>
        <div>
          <span className="font-medium text-foreground">Extraído (UTC):</span> {snap?.Extraido_Utc ?? "—"}
        </div>
        {snap?.SMS_Subcategories_Sample ? (
          <div className="mt-2">
            <span className="font-medium text-foreground">Amostra sms-*:</span> {snap.SMS_Subcategories_Sample}
          </div>
        ) : null}
      </div>

      {byCategoryMissing || !byCategoryCsvText ? (
        <div
          role="alert"
          className="rounded-lg border border-amber-500/50 bg-amber-500/10 px-4 py-3 text-sm text-amber-900 dark:text-amber-100"
        >
          O ficheiro <strong>conf_usage_billing_by_category.csv</strong> ainda não está disponível no repositório
          (ou o fetch falhou). Os cartões acima usam só o <strong>snapshot</strong>. Após o job{" "}
          <strong>Billing — Usage snapshot</strong> correr no GitHub, recarrega os dados.
        </div>
      ) : !showTable ? (
        <div
          role="status"
          className="rounded-lg border border-border bg-muted/30 px-4 py-3 text-sm text-muted-foreground"
        >
          Não há linhas de categorias para a conta <strong>{account}</strong> neste CSV. Verifica o job ou o
          filtro de conta.
        </div>
      ) : (
        <section>
          <h2 className="mb-2 text-lg font-medium">Categorias (Usage Records)</h2>
          <p className="mb-3 text-xs text-muted-foreground">
            Hierarquia por prefixo (ex. <code>sms</code> → <code>sms-outbound</code>). Métricas são as da API
            por categoria; não somar linhas pai+filho para totais globais.
          </p>
          <div className="rounded-lg border border-border">
            <div className="flex border-b border-border bg-muted/40 px-3 py-2 text-xs font-medium text-muted-foreground">
              <span className="flex-1">Categoria</span>
              <span className="w-20 text-right">Count</span>
              <span className="w-24 text-right">Usage</span>
              <span className="w-28 text-right">Price</span>
            </div>
            <CategoryRows nodes={tree} />
          </div>
        </section>
      )}

      {orgRow && (
        <section className="rounded-lg border border-dashed border-border p-4">
          <h3 className="text-sm font-medium text-muted-foreground">Todas as contas (soma)</h3>
          <div className="mt-2 text-lg font-semibold tabular-nums">
            Total USD: {orgRow.TotalPrice_Totalprice.toFixed(2)} · SMS count: {orgRow.SMS_Count} · SMS usage:{" "}
            {orgRow.SMS_Usage}
          </div>
        </section>
      )}
    </div>
  );
}
