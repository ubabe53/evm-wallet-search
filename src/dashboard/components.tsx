import { useId, type ReactNode } from "react";
import { Info, type LucideIcon } from "lucide-react";
import type { AccountType, CodeState, CounterpartySummary, WalletEvent } from "../data";
import { ACCOUNT_LABELS, type RankedCounterparty } from "./model";

export function EtherscanLink({
  href,
  title,
  children,
  className,
}: {
  href: string;
  title: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <a className={className} href={href} target="_blank" rel="noreferrer" title={title}>
      {children}
    </a>
  );
}

export function InfoTooltip({
  label,
  title,
  children,
  align = "right",
}: {
  label: string;
  title: string;
  children: ReactNode;
  align?: "left" | "right";
}) {
  const tooltipId = useId();
  return (
    <span className={`infoTooltip ${align}`}>
      <button
        className="infoTooltipTrigger"
        type="button"
        aria-label={label}
        aria-describedby={tooltipId}
      >
        <Info size={15} aria-hidden="true" />
      </button>
      <span className="infoTooltipContent" id={tooltipId} role="tooltip">
        <strong>{title}</strong>
        <span>{children}</span>
      </span>
    </span>
  );
}


export function Stat({ icon: Icon, label, value }: { icon: LucideIcon; label: string; value: string }) {
  return (
    <div className="stat">
      <Icon size={18} aria-hidden="true" />
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
    </div>
  );
}

type BadgeEvidence = {
  accountType: AccountType;
  codeState: CodeState;
  observationBlock: number | null;
  delegationTarget: string | null;
};

function AccountTypeBadge({ evidence }: { evidence: BadgeEvidence }) {
  if (evidence.accountType === "unknown") {
    return null;
  }
  const title = evidence.accountType === "eoa_candidate"
    ? evidence.codeState === "eip7702_delegated"
      ? `EOA with an exact EIP-7702 delegation indicator observed at pinned block ${evidence.observationBlock ?? "unknown"}${evidence.delegationTarget ? `; target ${evidence.delegationTarget}` : ""}`
      : `No bytecode observed at pinned block ${evidence.observationBlock ?? "unknown"}; this does not establish personhood or permanent EOA status`
    : `Contract bytecode observed at pinned block ${evidence.observationBlock ?? "unknown"}`;
  return <span className={`accountType ${evidence.accountType}`} title={title}>{ACCOUNT_LABELS[evidence.accountType]}</span>;
}

export function AccountBadges({ evidence }: { evidence: BadgeEvidence }) {
  return (
    <span className="accountBadges">
      <AccountTypeBadge evidence={evidence} />
    </span>
  );
}

export function summaryBadgeEvidence(row: CounterpartySummary | RankedCounterparty): BadgeEvidence {
  return {
    accountType: row.account_type,
    codeState: row.code_state,
    observationBlock: row.observation_block_number,
    delegationTarget: row.eip7702_delegation_target,
  };
}
export function eventBadgeEvidence(event: WalletEvent): BadgeEvidence {
  return {
    accountType: event.counterparty_account_type,
    codeState: event.counterparty_code_state,
    observationBlock: event.counterparty_observation_block_number,
    delegationTarget: event.counterparty_eip7702_delegation_target,
  };
}
