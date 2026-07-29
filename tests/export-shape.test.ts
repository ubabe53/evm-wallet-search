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
    expect("wallet_id" in metadata).toBe(false);
    expect(typeof metadata.ens).toBe("string");
    expect(events.every((event: Record<string, unknown>) =>
      !("wallet_id" in event) && !("ens" in event) &&
      typeof event.chain_id === "number" && typeof event.wallet_address === "string")).toBe(true);
    expect(summaries.tokens.every((row: Record<string, unknown>) =>
      !("wallet_id" in row) &&
      typeof row.chain_id === "number" && typeof row.wallet_address === "string")).toBe(true);
    expect(summaries.counterparties.every((row: Record<string, unknown>) =>
      !("wallet_id" in row) &&
      typeof row.chain_id === "number" && typeof row.wallet_address === "string")).toBe(true);
    expect(timeline.every((row: Record<string, unknown>) =>
      !("wallet_id" in row) &&
      typeof row.chain_id === "number" && typeof row.wallet_address === "string")).toBe(true);
    expect(["fixture", "hyperindex"]).toContain(metadata.data_source);
    expect(typeof metadata.is_sampled).toBe("boolean");
    expect(metadata.account_evidence_schema_version).toBeNull();
    expect(metadata.account_evidence_observation_block_number_min).toBeNull();
    expect(metadata.account_evidence_observation_block_number_max).toBeNull();
    expect(metadata.account_evidence_observation_block_timestamp_min).toBeNull();
    expect(metadata.account_evidence_observation_block_timestamp_max).toBeNull();
    expect(metadata.account_evidence_population_scope).toBe("distinct_nonzero_nonself_event_counterparties");
    expect(metadata.account_evidence_eligible_address_count).toBe(
      metadata.account_evidence_classified_address_count +
      metadata.account_evidence_failed_address_count +
      metadata.account_evidence_not_checked_address_count,
    );
    expect(metadata.account_evidence_eligible_event_count).toBe(
      metadata.account_evidence_classified_event_count +
      metadata.account_evidence_failed_event_count +
      metadata.account_evidence_not_checked_event_count,
    );
    expect(metadata.exported_event_count).toBeLessThanOrEqual(
      metadata.event_export_limit_per_recognition_account_evidence * metadata.recognition_account_evidence_cell_count,
    );
    expect(metadata.exported_interaction_count).toBeLessThanOrEqual(
      metadata.graph_interaction_export_limit_per_recognition_account_evidence * metadata.recognition_account_evidence_cell_count,
    );
    expect(metadata.exported_timeline_row_count).toBeLessThanOrEqual(
      metadata.timeline_row_export_limit_per_recognition_account_evidence * metadata.recognition_account_evidence_cell_count,
    );
    expect(metadata.token_summary_ranking_limit_per_recognition_account_selection).toBe(500);
    expect(metadata.token_summary_ranking_selection_count).toBe(9);
    expect(metadata.token_summary_ranking_candidate_token_count).toBeGreaterThan(0);
    expect(metadata.token_summary_rankings_exact_for_all_filter_selections).toBe(true);
    expect(metadata.counterparty_ranking_limit_per_recognition_account_selection).toBe(50);
    expect(metadata.counterparty_recognition_combination_count).toBe(3);
    expect(metadata.counterparty_account_filter_combination_count).toBe(3);
    expect(metadata.counterparty_ranking_selection_count).toBe(9);
    expect(metadata.counterparty_rankings_exact_for_all_filter_selections).toBe(true);
    expect(metadata.exported_event_count).toBeLessThanOrEqual(metadata.transfer_count);
    expect(metadata.exported_interaction_count).toBeLessThanOrEqual(metadata.interaction_count);
    expect(metadata.exported_token_summary_count).toBeLessThanOrEqual(metadata.token_summary_row_count);
    expect(metadata.exported_counterparty_summary_count).toBeLessThanOrEqual(metadata.counterparty_summary_row_count);
    expect(metadata.exported_timeline_row_count).toBeLessThanOrEqual(metadata.timeline_row_count);
    expect(graph.edges.length).toBe(metadata.exported_interaction_count * 2);
    expect(Object.keys(events[0]).sort()).toEqual([
      "block_number",
      "block_timestamp",
      "chain_id",
      "counterparty_account_type",
      "counterparty_address",
      "counterparty_code_state",
      "counterparty_eip7702_delegation_target",
      "counterparty_observation_block_number",
      "direction",
      "is_indirect",
      "log_index",
      "recognition_status",
      "token_address",
      "token_name",
      "token_symbol",
      "transaction_hash",
      "transaction_index",
      "transfer_id",
      "wallet_address",
    ]);
    expect(Object.keys(summaries.tokens[0]).sort()).toEqual([
      "chain_id",
      "counterparty_account_type",
      "counterparty_count",
      "inbound_transfer_count",
      "indirect_inbound_transfer_count",
      "indirect_outbound_transfer_count",
      "outbound_transfer_count",
      "recipient_account_count",
      "recognition_status",
      "self_transfer_count",
      "sender_account_count",
      "token_address",
      "token_name",
      "token_symbol",
      "transfer_count",
      "wallet_address",
    ]);
    expect(Object.keys(summaries.counterparties[0]).sort()).toEqual([
      "account_type",
      "chain_id",
      "code_state",
      "counterparty_address",
      "eip7702_delegation_target",
      "first_seen_at",
      "inbound_transfer_count",
      "last_seen_at",
      "observation_block_number",
      "outbound_transfer_count",
      "recognition_status",
      "token_count",
      "transfer_count",
      "wallet_address",
    ]);
    expect(Object.keys(timeline[0]).sort()).toEqual([
      "block_date",
      "chain_id",
      "counterparty_account_type",
      "direction",
      "recognition_status",
      "token_address",
      "token_symbol",
      "transfer_count",
      "wallet_address",
    ]);
    expect(["recognized", "other"]).toContain(summaries.tokens[0].recognition_status);
    expect(summaries.tokens.every((row: {
      transfer_count: number;
      inbound_transfer_count: number;
      outbound_transfer_count: number;
      self_transfer_count: number;
      indirect_inbound_transfer_count: number;
      indirect_outbound_transfer_count: number;
      counterparty_count: number;
      sender_account_count: number;
      recipient_account_count: number;
    }) =>
      row.counterparty_count >= 0 &&
      row.sender_account_count >= 0 &&
      row.recipient_account_count >= 0 &&
      row.counterparty_count >= row.sender_account_count &&
      row.counterparty_count >= row.recipient_account_count &&
      row.counterparty_count <= row.sender_account_count + row.recipient_account_count &&
      row.indirect_inbound_transfer_count <= row.inbound_transfer_count &&
      row.indirect_outbound_transfer_count <= row.outbound_transfer_count &&
      row.transfer_count ===
        row.inbound_transfer_count + row.outbound_transfer_count + row.self_transfer_count)).toBe(true);
    expect(summaries.counterparties.every((row: {
      counterparty_address: string;
      wallet_address: string;
      recognition_status: string;
      transfer_count: number;
      inbound_transfer_count: number;
      outbound_transfer_count: number;
    }) =>
      row.counterparty_address !== "0x0000000000000000000000000000000000000000" &&
      row.counterparty_address !== row.wallet_address &&
      ["recognized", "other"].includes(row.recognition_status) &&
      row.transfer_count === row.inbound_transfer_count + row.outbound_transfer_count)).toBe(true);
    expect(graph.edges.every((edge: { data: { recognitionStatus: string } }) =>
      ["recognized", "other"].includes(edge.data.recognitionStatus))).toBe(true);
    expect(metadata.recognition_counts["recognized+other"].transfer_count).toBe(metadata.transfer_count);
    expect(metadata.recognition_account_counts[
      "recognized+other|eoa_candidate+contract"
    ].transfer_count).toBe(metadata.transfer_count);

    const endpoints = new Set(graph.edges.flatMap((edge: { data: { source: string; target: string } }) => [edge.data.source, edge.data.target]));
    expect(graph.nodes.every((node: { data: { id: string } }) => endpoints.has(node.data.id))).toBe(true);
    const accountTypes = ["eoa_candidate", "contract", "unknown"];
    expect(graph.nodes.every((node: { data: { type: string; accountType: string | null } }) =>
      node.data.type !== "counterparty" || accountTypes.includes(node.data.accountType ?? ""))).toBe(true);
    expect(events.every((event: { counterparty_account_type: string }) =>
      accountTypes.includes(event.counterparty_account_type))).toBe(true);
    expect(new Set(summaries.counterparties.map((row: { account_type: string }) => row.account_type))).toEqual(
      new Set(["unknown"]),
    );
    expect(events.every((event: {
      transfer_id: string;
      transaction_hash: string;
      transaction_index: number;
      log_index: number;
      is_indirect: boolean | null;
    }) =>
      event.transfer_id === `1-${event.transaction_hash}-${event.log_index}` &&
      Number.isInteger(event.transaction_index) &&
      (event.is_indirect == null || typeof event.is_indirect === "boolean"))).toBe(true);
    expect(graph.edges.every((edge: { data: { transferCount: number; counterpartyTransferCount: number } }) =>
      edge.data.counterpartyTransferCount >= edge.data.transferCount)).toBe(true);
    expect(graph.edges.every((edge: { data: { counterpartyAccountType: string } }) =>
      accountTypes.includes(edge.data.counterpartyAccountType))).toBe(true);
  });
});
