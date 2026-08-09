import { ArrowDownLeft, ArrowUpRight } from "lucide-react";
import {
  compactAddress,
  etherscanAddressUrl,
  type RankedCounterparty,
} from "./model";
import { AccountBadges, EtherscanLink, summaryBadgeEvidence } from "./components";

export function CounterpartyTable({ rows }: { rows: RankedCounterparty[] }) {
  return (
    <table className="counterpartyTable">
      <thead>
        <tr>
          <th>#</th>
          <th>Account</th>
          <th>Activity</th>
          <th title="Captured Transfer-signature event counts relative to the tracked wallet">
            Inbound / Outbound Events
          </th>
        </tr>
      </thead>
      <tbody>
        {rows.length === 0 && (
          <tr>
            <td className="tableEmpty" colSpan={4}>No counterparties match</td>
          </tr>
        )}
        {rows.map((row, index) => (
          <tr key={row.counterparty_address}>
            <td className="rankCell" aria-label={`Rank ${index + 1}`}>{index + 1}</td>
            <td className="accountCell" data-label={`#${index + 1} Account`}>
              <div>
                <EtherscanLink
                  className="addressLink"
                  href={etherscanAddressUrl(row.counterparty_address)}
                  title={`View ${row.counterparty_address} on Etherscan`}
                >
                  <code>{compactAddress(row.counterparty_address)}</code>
                </EtherscanLink>
                <AccountBadges evidence={summaryBadgeEvidence(row)} />
              </div>
              <small>Last active {new Date(row.last_seen_at).toLocaleDateString()}</small>
            </td>
            <td className="activityCell" data-label="Activity">
              <strong>{row.transfer_count.toLocaleString("en-US")}</strong>
              <small>{row.token_count.toLocaleString("en-US")} {row.token_count === 1 ? "token" : "tokens"}</small>
            </td>
            <td className="counterpartyDirectionCell" data-label="Inbound / Outbound">
              <span
                className="flowIndicator"
                title={`${row.inbound_transfer_count.toLocaleString("en-US")} inbound, ${row.outbound_transfer_count.toLocaleString("en-US")} outbound Transfer events`}
              >
                <span className="direction in"><ArrowDownLeft size={13} />{row.inbound_transfer_count.toLocaleString("en-US")}</span>
                <i aria-hidden="true">|</i>
                <span className="direction out"><ArrowUpRight size={13} />{row.outbound_transfer_count.toLocaleString("en-US")}</span>
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
