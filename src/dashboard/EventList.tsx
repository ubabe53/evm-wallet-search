import {
  ArrowDownLeft,
  ArrowUpRight,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  Repeat2,
} from "lucide-react";
import type { WalletEvent } from "../data";
import {
  EVENT_PAGE_SIZE,
  INDIRECT_TRANSFER_EXPLANATION,
  SELF_TRANSFER_EXPLANATION,
  etherscanAddressUrl,
  etherscanTokenUrl,
  etherscanTransactionUrl,
  shortAddress,
} from "./model";
import { AccountBadges, EtherscanLink, eventBadgeEvidence } from "./components";

export function EventList({
  events,
  limit,
  totalCount,
  showMoreDisabled,
  onShowMore,
  onShowLess,
}: {
  events: WalletEvent[];
  limit: number;
  totalCount: number;
  showMoreDisabled: boolean;
  onShowMore: () => void;
  onShowLess: () => void;
}) {
  const visibleEvents = events.slice(0, limit);
  const canShowLess = limit > EVENT_PAGE_SIZE && events.length > EVENT_PAGE_SIZE;
  const canShowMore = visibleEvents.length < totalCount;

  return (
    <div className="events">
      {visibleEvents.length === 0 && <div className="listEmpty">No events match</div>}
      {visibleEvents.map((event) => (
        <article key={event.transfer_id} className="event">
          <div>
            <strong>
              <EtherscanLink
                className="etherscanLink"
                href={etherscanTokenUrl(event.token_address)}
                title={`View ${event.token_symbol ?? event.token_address} on Etherscan`}
              >
                {event.token_symbol ?? shortAddress(event.token_address)}
              </EtherscanLink>
            </strong>
            <span>{new Date(event.block_timestamp).toLocaleString()}</span>
            <EtherscanLink
              className="transactionLink"
              href={etherscanTransactionUrl(event.transaction_hash)}
              title="View transaction on Etherscan"
            >
              <ExternalLink size={14} aria-hidden="true" />
              <span className="srOnly">View transaction on Etherscan</span>
            </EtherscanLink>
          </div>
          <div>
            <span
              className={`direction ${event.direction}`}
              title={
                event.direction === "self"
                  ? SELF_TRANSFER_EXPLANATION
                  : event.is_indirect
                    ? INDIRECT_TRANSFER_EXPLANATION
                    : undefined
              }
            >
              {event.direction === "in"
                ? <ArrowDownLeft size={14} />
                : event.direction === "out"
                  ? <ArrowUpRight size={14} />
                  : <Repeat2 size={14} />}
              {event.direction}{event.direction !== "self" && event.is_indirect ? "*" : ""}
            </span>
            <EtherscanLink
              className="addressLink"
              href={etherscanAddressUrl(event.counterparty_address)}
              title={`View ${event.counterparty_address} on Etherscan`}
            >
              <code>{event.direction === "self" ? "same wallet" : shortAddress(event.counterparty_address)}</code>
            </EtherscanLink>
            <AccountBadges evidence={eventBadgeEvidence(event)} />
          </div>
        </article>
      ))}
      {(canShowLess || canShowMore) && (
        <div className="eventControls">
          {canShowLess && (
            <button className="eventPageButton" type="button" onClick={onShowLess}>
              <ChevronUp size={16} />
              Show less
            </button>
          )}
          {canShowMore && (
            <button className="eventPageButton" type="button" onClick={onShowMore} disabled={showMoreDisabled}>
              <ChevronDown size={16} />
              Show more
            </button>
          )}
        </div>
      )}
    </div>
  );
}
