import { describe, expect, it } from "vitest";
import type { CounterpartySummary, TimelineRow, TokenSummary } from "../src/data";
import {
  accountEvidenceCoverageDescription,
  accountEvidenceCoverageLabel,
  accountEvidenceObservationBlockLabel,
  accountEvidenceObservationTimeLabel,
  accountMatches,
  aggregateCounterparties,
  aggregateTimelineRows,
  aggregateTokenSummaries,
  bucketTimelineRows,
  etherscanAddressUrl,
  etherscanTokenUrl,
  etherscanTransactionUrl,
  scanStageLabel,
  snapshotCoverageLabel,
  timelineScaleTicks,
  timelineYears,
} from "../src/dashboard/model";
import { metadata, summaries, timeline } from "./dashboard-fixtures";

describe("dashboard model", () => {
  it("labels scan stages without presenting coarse adapter checkpoints as percentages", () => {
    expect(scanStageLabel({ status: "queued", progress: 0 })).toBe("Queued");
    expect(scanStageLabel({ status: "running", progress: 1 })).toBe("Preparing scan");
    expect(scanStageLabel({ status: "running", progress: 5 })).toBe("Indexing and building analytics");
    expect(scanStageLabel({ status: "running", progress: 95 })).toBe("Validating and publishing");
    expect(scanStageLabel({ status: "completed", progress: 100 })).toBe("Complete");
    expect(scanStageLabel({ status: "failed", progress: 0 })).toBe("Failed");
  });

  it("exposes binary account filters while retaining unresolved rows in the all selection", () => {
    expect(accountMatches("eoa_candidate", ["eoa_candidate"])).toBe(true);
    expect(accountMatches("contract", ["eoa_candidate"])).toBe(false);
    expect(accountMatches("unknown", ["eoa_candidate", "contract"])).toBe(true);
  });

  it("renders single and mixed address-type observation ranges", () => {
    expect(accountEvidenceObservationBlockLabel(22_500_000, 22_500_000)).toBe("block 22,500,000");
    expect(accountEvidenceObservationBlockLabel(22_500_000, 22_600_000)).toBe("blocks 22,500,000–22,600,000");
    expect(accountEvidenceObservationTimeLabel("2025-05-17T03:11:47+00:00", "2025-05-17T03:11:47+00:00"))
      .toBe("2025-05-17T03:11:47+00:00");
    expect(accountEvidenceObservationTimeLabel("2025-05-17T03:11:47+00:00", "2025-05-18T03:11:47+00:00"))
      .toBe("2025-05-17T03:11:47+00:00–2025-05-18T03:11:47+00:00");
  });

  it("shows account coverage with explicit address and event denominators", () => {
    expect(accountEvidenceCoverageLabel(metadata)).toBe("address types 2/3");
    expect(accountEvidenceCoverageDescription(metadata)).toContain(
      "2 of 3 nonzero, nonself counterparties classified (66.7%)",
    );
    expect(accountEvidenceCoverageDescription(metadata)).toContain(
      "3 of 4 captured transfers have classified counterparties (75%)",
    );
    expect(accountEvidenceCoverageDescription(metadata)).toContain("0 failed; 1 not checked");
  });

  it("labels only verified finalized snapshot coverage", () => {
    expect(snapshotCoverageLabel({
      snapshot_start_block: 3,
      snapshot_end_block: 25_523_374,
      snapshot_finality_policy: "ethereum_finalized",
    })).toBe("Blocks 3–25,523,374 · Finalized");
    expect(snapshotCoverageLabel({
      snapshot_start_block: null,
      snapshot_end_block: null,
      snapshot_finality_policy: null,
    })).toBe("Coverage not recorded");
  });

  it("aggregates token classification rows into one transfer-ranked counterparty", () => {
    const base = summaries.counterparties[0] as unknown as CounterpartySummary;
    const rows = aggregateCounterparties([
      base,
      {
        ...base,
        recognition_status: "other" as const,
        transfer_count: 2,
        inbound_transfer_count: 0,
        outbound_transfer_count: 2,
        token_count: 1,
      },
    ]);

    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      transfer_count: 5,
      inbound_transfer_count: 2,
      outbound_transfer_count: 3,
      token_count: 3,
    });
  });

  it("aggregates matching account cells back to token grain before ranking", () => {
    const base = summaries.tokens[0] as unknown as TokenSummary;
    const rows = aggregateTokenSummaries([
      { ...base, counterparty_account_type: "contract", transfer_count: 60 },
      {
        ...base,
        counterparty_account_type: "eoa_candidate",
        transfer_count: 60,
      },
      {
        ...base,
        token_address: "0xbbb",
        token_symbol: "BBB",
        counterparty_account_type: "contract",
        transfer_count: 100,
      },
    ]);

    expect(rows.map((row) => [row.token_address, row.transfer_count])).toEqual([
      ["0x2", 120],
      ["0xbbb", 100],
    ]);
  });

  it("aggregates account cells back to the displayed daily token-direction grain", () => {
    const base = timeline[0] as unknown as TimelineRow;
    const rows = aggregateTimelineRows([
      { ...base, counterparty_account_type: "contract", transfer_count: 2 },
      {
        ...base,
        counterparty_account_type: "eoa_candidate",
        transfer_count: 3,
      },
    ]);

    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ transfer_count: 5 });
  });

  it("buckets timeline rows into fixed yearly overviews and selected-year months", () => {
    const rows = [
      { block_date: "2023-11-14", direction: "in", transfer_count: 2 },
      { block_date: "2023-11-16", direction: "out", transfer_count: 3 },
      { block_date: "2023-11-18", direction: "self", transfer_count: 1 },
    ] as const;

    const years = bucketTimelineRows(rows, "year", null, [2022, 2023, 2024]);
    expect(years).toHaveLength(3);
    expect(years[0]).toMatchObject({
      bucket_start: "2022-01-01",
      transfer_count: 0,
    });
    expect(years[1]).toMatchObject({
      bucket_start: "2023-01-01",
      bucket_end: "2024-01-01",
      transfer_count: 6,
      self_transfer_count: 1,
    });

    const months = bucketTimelineRows(rows, "month", 2023);
    expect(months).toHaveLength(12);
    expect(months[0]).toMatchObject({
      bucket_start: "2023-01-01",
      transfer_count: 0,
    });
    expect(months[10]).toMatchObject({
      bucket_start: "2023-11-01",
      bucket_end: "2023-12-01",
      transfer_count: 6,
      self_transfer_count: 1,
    });
    expect(timelineYears("2022-02-01T00:00:00Z", "2024-07-01T00:00:00Z"))
      .toEqual([2022, 2023, 2024]);
    expect(timelineScaleTicks(100)).toEqual([100, 75, 50, 25, 0]);
  });


  it("builds canonical Etherscan routes", () => {
    expect(etherscanAddressUrl("0xabc")).toBe("https://etherscan.io/address/0xabc");
    expect(etherscanTokenUrl("0xdef")).toBe("https://etherscan.io/token/0xdef");
    expect(etherscanTransactionUrl("0x123")).toBe("https://etherscan.io/tx/0x123");
  });
});
