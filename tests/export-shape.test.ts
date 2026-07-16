import { describe, expect, it } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

const dataPath = (name: string) => join(process.cwd(), "public", "data", name);

describe("dashboard export shape", () => {
  it("contains graph, summary, timeline, and event JSON after export", () => {
    for (const file of ["graph.json", "summaries.json", "timeline.json", "events.json", "meta.json"]) {
      expect(existsSync(dataPath(file))).toBe(true);
    }

    const graph = JSON.parse(readFileSync(dataPath("graph.json"), "utf8"));
    const summaries = JSON.parse(readFileSync(dataPath("summaries.json"), "utf8"));
    const timeline = JSON.parse(readFileSync(dataPath("timeline.json"), "utf8"));
    const events = JSON.parse(readFileSync(dataPath("events.json"), "utf8"));
    const metadata = JSON.parse(readFileSync(dataPath("meta.json"), "utf8"));

    expect(Array.isArray(graph.nodes)).toBe(true);
    expect(Array.isArray(graph.edges)).toBe(true);
    expect(Array.isArray(summaries.tokens)).toBe(true);
    expect(Array.isArray(summaries.counterparties)).toBe(true);
    expect(Array.isArray(timeline)).toBe(true);
    expect(["fixture", "hyperindex"]).toContain(metadata.data_source);
    expect(typeof metadata.is_sampled).toBe("boolean");
    expect(metadata.exported_event_count).toBeLessThanOrEqual(metadata.event_export_limit_per_status * 4);
    expect(metadata.exported_interaction_count).toBeLessThanOrEqual(metadata.graph_interaction_export_limit_per_status * 4);
    expect(metadata.exported_token_summary_count).toBeLessThanOrEqual(metadata.token_summary_export_limit_per_status * 4);
    expect(metadata.exported_counterparty_summary_count).toBeLessThanOrEqual(
      metadata.counterparty_ranking_limit_per_status_combination * 15 * 4,
    );
    expect(metadata.exported_timeline_row_count).toBeLessThanOrEqual(metadata.timeline_row_export_limit);
    expect(metadata.exported_event_count).toBeLessThanOrEqual(metadata.transfer_count);
    expect(metadata.exported_interaction_count).toBeLessThanOrEqual(metadata.interaction_count);
    expect(metadata.exported_token_summary_count).toBeLessThanOrEqual(metadata.token_summary_row_count);
    expect(metadata.exported_counterparty_summary_count).toBeLessThanOrEqual(metadata.counterparty_summary_row_count);
    expect(metadata.exported_timeline_row_count).toBeLessThanOrEqual(metadata.timeline_row_count);
    expect(graph.edges.length).toBe(metadata.exported_interaction_count * 2);
    expect(typeof summaries.tokens[0].value_raw_sum).toBe("string");
    expect(["trusted", "unverified", "suspected_spam", "spam"]).toContain(summaries.tokens[0].token_status);
    expect(summaries.tokens.every((row: {
      token_reputation_score: number;
      transfer_count: number;
      inbound_transfer_count: number;
      outbound_transfer_count: number;
      counterparty_count: number;
      sender_account_count: number;
      recipient_account_count: number;
    }) =>
      row.token_reputation_score >= 0 &&
      row.counterparty_count >= 0 &&
      row.sender_account_count >= 0 &&
      row.recipient_account_count >= 0 &&
      row.counterparty_count >= row.sender_account_count &&
      row.counterparty_count >= row.recipient_account_count &&
      row.counterparty_count <= row.sender_account_count + row.recipient_account_count &&
      row.transfer_count === row.inbound_transfer_count + row.outbound_transfer_count)).toBe(true);
    expect(summaries.counterparties.every((row: {
      counterparty_address: string;
      wallet_address: string;
      token_status: string;
      transfer_count: number;
      inbound_transfer_count: number;
      outbound_transfer_count: number;
    }) =>
      row.counterparty_address !== "0x0000000000000000000000000000000000000000" &&
      row.counterparty_address !== row.wallet_address &&
      ["trusted", "unverified", "suspected_spam", "spam"].includes(row.token_status) &&
      row.transfer_count === row.inbound_transfer_count + row.outbound_transfer_count)).toBe(true);
    expect(graph.edges.every((edge: { data: { tokenStatus: string } }) =>
      ["trusted", "unverified", "suspected_spam", "spam"].includes(edge.data.tokenStatus))).toBe(true);
    expect(metadata.non_spam_transfer_count + metadata.spam_transfer_count).toBe(metadata.transfer_count);
    expect(metadata.spam_token_count).toBeLessThanOrEqual(metadata.token_count);
    expect(metadata.status_counts["trusted+unverified+suspected_spam+spam"].transfer_count).toBe(metadata.transfer_count);

    const endpoints = new Set(graph.edges.flatMap((edge: { data: { source: string; target: string } }) => [edge.data.source, edge.data.target]));
    expect(graph.nodes.every((node: { data: { id: string } }) => endpoints.has(node.data.id))).toBe(true);
    expect(graph.edges.every((edge: { data: { amountDecimalSum: number | null } }) => edge.data.amountDecimalSum == null || typeof edge.data.amountDecimalSum === "number")).toBe(true);
    expect(graph.nodes.every((node: { data: { type: string; addressType: string | null } }) =>
      node.data.type === "token" || ["contract", "wallet", "unknown"].includes(node.data.addressType ?? ""))).toBe(true);
    expect(events.every((event: { counterparty_type: string }) =>
      ["contract", "wallet", "unknown"].includes(event.counterparty_type))).toBe(true);
    expect(graph.edges.every((edge: { data: { transferCount: number; counterpartyTransferCount: number } }) =>
      edge.data.counterpartyTransferCount >= edge.data.transferCount)).toBe(true);
  });
});
