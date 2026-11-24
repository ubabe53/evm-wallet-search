import type { CounterpartySummary, DashboardData, DashboardMetadata, WalletEvent } from "../data";
import type { DisplayedTokenSummary } from "./model";

const ZERO_ADDRESS = "0x0000000000000000000000000000000000000000";

function isExternalCounterparty(event: WalletEvent): boolean {
  return event.counterparty_address !== ZERO_ADDRESS &&
    event.counterparty_address !== event.wallet_address;
}

function groupEvents(events: WalletEvent[], key: "token_address" | "counterparty_address") {
  const groups = new Map<string, WalletEvent[]>();
  for (const event of events) {
    const address = event[key];
    const group = groups.get(address);
    if (group) {
      group.push(event);
    } else {
      groups.set(address, [event]);
    }
  }
  return groups.values();
}

function summarizeTokens(events: WalletEvent[]): DisplayedTokenSummary[] {
  return Array.from(groupEvents(events, "token_address"), (group) => {
    const first = group[0];
    const senders = new Set<string>();
    const recipients = new Set<string>();
    let inbound = 0;
    let outbound = 0;
    let indirectInbound = 0;
    let indirectOutbound = 0;

    for (const event of group) {
      if (event.direction === "in") {
        inbound += 1;
        indirectInbound += Number(event.is_indirect === true);
        if (isExternalCounterparty(event)) senders.add(event.counterparty_address);
      } else if (event.direction === "out") {
        outbound += 1;
        indirectOutbound += Number(event.is_indirect === true);
        if (isExternalCounterparty(event)) recipients.add(event.counterparty_address);
      }
    }

    return {
      chain_id: first.chain_id,
      wallet_address: first.wallet_address,
      token_address: first.token_address,
      token_symbol: first.token_symbol ?? first.token_address.slice(0, 10),
      token_name: first.token_name,
      recognition_status: first.recognition_status,
      transfer_count: group.length,
      inbound_transfer_count: inbound,
      outbound_transfer_count: outbound,
      self_transfer_count: group.length - inbound - outbound,
      indirect_inbound_transfer_count: indirectInbound,
      indirect_outbound_transfer_count: indirectOutbound,
      counterparty_count: new Set([...senders, ...recipients]).size,
      sender_account_count: senders.size,
      recipient_account_count: recipients.size,
    };
  });
}

function summarizeCounterparties(events: WalletEvent[]): CounterpartySummary[] {
  return Array.from(groupEvents(events, "counterparty_address"), (group) => {
    const first = group[0];
    const tokens = new Set<string>();
    let inbound = 0;
    let firstSeen = Date.parse(first.block_timestamp);
    let lastSeen = firstSeen;

    for (const event of group) {
      tokens.add(event.token_address);
      inbound += Number(event.direction === "in");
      const timestamp = Date.parse(event.block_timestamp);
      firstSeen = Math.min(firstSeen, timestamp);
      lastSeen = Math.max(lastSeen, timestamp);
    }

    return {
      chain_id: first.chain_id,
      wallet_address: first.wallet_address,
      counterparty_address: first.counterparty_address,
      account_type: first.counterparty_account_type,
      code_state: first.counterparty_code_state,
      observation_block_number: first.counterparty_observation_block_number,
      eip7702_delegation_target: first.counterparty_eip7702_delegation_target,
      transfer_count: group.length,
      inbound_transfer_count: inbound,
      outbound_transfer_count: group.length - inbound,
      token_count: tokens.size,
      first_seen_at: new Date(firstSeen).toISOString(),
      last_seen_at: new Date(lastSeen).toISOString(),
    };
  });
}

export function searchStaticEvents(
  data: Pick<DashboardData<DashboardMetadata>, "events" | "summaries" | "metadata">,
  visibleEvents: WalletEvent[],
  normalizedQuery: string,
) {
  const events = visibleEvents.filter((event) =>
    [
      event.transaction_hash,
      event.wallet_address,
      event.counterparty_address,
      event.token_address,
      event.token_symbol,
      event.token_name,
    ].some((value) => value?.toLowerCase().includes(normalizedQuery)),
  );
  const exportedTokenCounterparties = "token_contract_counterparties" in data.metadata
    ? data.metadata.token_contract_counterparties
    : undefined;
  const tokenAddresses = new Set(exportedTokenCounterparties ??
    data.events.map((event) => event.token_address));
  // Older bounded exports can only prove eligibility for their precomputed ranking candidates.
  const knownEligible = exportedTokenCounterparties === undefined &&
    data.events.length < data.metadata.transfer_count
    ? new Set(data.summaries.counterparties.map((row) => row.counterparty_address))
    : null;
  const counterpartyEvents = events.filter((event) =>
    isExternalCounterparty(event) &&
    !tokenAddresses.has(event.counterparty_address) &&
    (knownEligible === null || knownEligible.has(event.counterparty_address))
  );

  return {
    events,
    summaries: {
      tokens: summarizeTokens(events),
      counterparties: summarizeCounterparties(counterpartyEvents),
    },
    timeline: events.map((event) => ({
      block_date: new Date(event.block_timestamp).toISOString().slice(0, 10),
      direction: event.direction,
      transfer_count: 1,
    })),
  };
}
