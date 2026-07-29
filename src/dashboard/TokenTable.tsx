import { ArrowDownLeft, ArrowUpRight, ExternalLink, Repeat2 } from "lucide-react";
import type { RecognitionStatus } from "../data";
import {
  INDIRECT_TRANSFER_EXPLANATION,
  etherscanTokenUrl,
  shortAddress,
  type DisplayedTokenSummary,
} from "./model";
import { EtherscanLink, InfoTooltip } from "./components";

export function TokenTable({
  rows,
  editable,
  updatingToken,
  onRecognitionChange,
}: {
  rows: DisplayedTokenSummary[];
  editable: boolean;
  updatingToken: string | null;
  onRecognitionChange: (row: DisplayedTokenSummary, value: RecognitionStatus | "automatic") => void;
}) {
  const rankedRows = [...rows].sort((left, right) =>
    right.transfer_count - left.transfer_count ||
    left.token_address.localeCompare(right.token_address),
  );
  const maximumTransferCount = Math.max(
    ...rankedRows.map((row) => row.transfer_count),
    0,
  );

  return (
    <table className="tokenActivityTable">
      <thead>
        <tr>
          <th>Token</th>
          <th title="Captured Transfer-signature event count">Activity</th>
          <th title="Captured Transfer-signature event counts relative to the tracked wallet">
            Direction
          </th>
          <th>Counterparties</th>
          <th aria-label="Recognition">
            <span className="tableHeaderInfo">
              Recognition
              <InfoTooltip label="How token recognition works" title="Recognition controls" align="left">
                Automatic uses the stored exact-address registry or reviewed seed result. Recognized
                and Other save a local override in this dashboard; choosing Automatic removes it.
              </InfoTooltip>
            </span>
          </th>
        </tr>
      </thead>
      <tbody>
        {rankedRows.length === 0 && (
          <tr>
            <td className="tableEmpty" colSpan={5}>No token activity matches</td>
          </tr>
        )}
        {rankedRows.map((row, index) => (
          <tr key={row.token_address}>
            <td>
              <div className="tokenIdentityCell">
                <span className="rankCell">{index + 1}</span>
                <div>
                  <div className="tokenIdentityPrimary">
                    <EtherscanLink
                      className="etherscanLink"
                      href={etherscanTokenUrl(row.token_address)}
                      title={`View ${row.token_symbol} on Etherscan`}
                    >
                      {row.token_symbol}
                    </EtherscanLink>
                    {row.token_name && <span title={row.token_name}>{row.token_name}</span>}
                  </div>
                  <EtherscanLink
                    className="tokenContractLink"
                    href={etherscanTokenUrl(row.token_address)}
                    title={`View contract ${row.token_address} on Etherscan`}
                  >
                    <code>{shortAddress(row.token_address)}</code>
                    <ExternalLink size={11} aria-hidden="true" />
                  </EtherscanLink>
                </div>
              </div>
            </td>
            <td className="tokenActivityCell">
              <strong>{row.transfer_count.toLocaleString("en-US")}</strong>
              <div
                className="tokenActivityBar"
                title={`${row.transfer_count.toLocaleString("en-US")} captured Transfer-signature events`}
              >
                <span
                  aria-hidden="true"
                  style={{
                    width: maximumTransferCount === 0
                      ? "0%"
                      : `${row.transfer_count / maximumTransferCount * 100}%`,
                  }}
                />
              </div>
            </td>
            <td className="tokenDirectionCell">
              <span className="flowIndicator">
                <span className="direction in"><ArrowDownLeft size={13} />In {row.inbound_transfer_count.toLocaleString("en-US")}</span>
                <i aria-hidden="true">|</i>
                <span className="direction out"><ArrowUpRight size={13} />Out {row.outbound_transfer_count.toLocaleString("en-US")}</span>
                <i aria-hidden="true">|</i>
                <span className="direction self"><Repeat2 size={13} />Self {(row.self_transfer_count ?? 0).toLocaleString("en-US")}</span>
              </span>
              <small title={INDIRECT_TRANSFER_EXPLANATION}>
                Indirect {row.indirect_inbound_transfer_count.toLocaleString("en-US")} in · {row.indirect_outbound_transfer_count.toLocaleString("en-US")} out
              </small>
            </td>
            <td className="tokenCounterpartyCell">
              <strong>{row.counterparty_count.toLocaleString("en-US")}</strong>
              <small
                title={`${row.sender_account_count.toLocaleString("en-US")} distinct non-zero sender accounts, ${row.recipient_account_count.toLocaleString("en-US")} distinct non-zero recipient accounts`}
              >
                {row.sender_account_count.toLocaleString("en-US")} senders · {row.recipient_account_count.toLocaleString("en-US")} recipients
              </small>
            </td>
            <td>
              <div className="recognitionCell">
                <span className={`recognitionStatus ${row.recognition_status}`}>
                  {row.recognition_status === "recognized" ? "Recognized" : "Other"}
                </span>
                <select
                  aria-label={`Recognition for ${row.token_symbol}`}
                  value={row.recognition_override_status ?? "automatic"}
                  disabled={!editable || updatingToken === row.token_address}
                  title={editable ? "Set a local recognition override" : "Manual overrides are available in live API mode"}
                  onChange={(event) => onRecognitionChange(
                    row,
                    event.target.value as RecognitionStatus | "automatic",
                  )}
                >
                  <option value="automatic">Automatic</option>
                  <option value="recognized">Recognized</option>
                  <option value="other">Other</option>
                </select>
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
