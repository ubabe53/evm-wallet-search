with token_contracts as (
  select distinct token_address
  from {{ ref('wallet_events') }}
),
eligible_events as (
  select events.*
  from {{ ref('wallet_events') }} as events
  left join token_contracts
    on events.counterparty_address = token_contracts.token_address
  where events.counterparty_address != '0x0000000000000000000000000000000000000000'
    and events.counterparty_address != events.wallet_address
    and token_contracts.token_address is null
)
select
  wallet_id,
  wallet_address,
  chain_id,
  counterparty_address,
  any_value(counterparty_account_type) as account_type,
  any_value(counterparty_code_state) as code_state,
  any_value(counterparty_code_size_bytes) as code_size_bytes,
  any_value(counterparty_observation_block_number) as observation_block_number,
  any_value(counterparty_observation_block_timestamp) as observation_block_timestamp,
  any_value(counterparty_eip7702_delegation_target) as eip7702_delegation_target,
  bool_or(counterparty_is_safe) as is_safe,
  any_value(counterparty_safe_verification_status) as safe_verification_status,
  any_value(counterparty_safe_version) as safe_version,
  any_value(counterparty_safe_singleton_address) as safe_singleton_address,
  any_value(counterparty_safe_owner_count) as safe_owner_count,
  any_value(counterparty_safe_threshold) as safe_threshold,
  bool_or(counterparty_is_erc4337_account) as is_erc4337_account,
  any_value(counterparty_erc4337_user_operation_count) as erc4337_user_operation_count,
  any_value(counterparty_erc4337_first_observed_block) as erc4337_first_observed_block,
  any_value(counterparty_erc4337_last_observed_block) as erc4337_last_observed_block,
  any_value(counterparty_erc4337_entrypoint_address) as erc4337_entrypoint_address,
  any_value(counterparty_erc4337_entrypoint_version) as erc4337_entrypoint_version,
  any_value(counterparty_erc4337_entrypoint_source) as erc4337_entrypoint_source,
  any_value(counterparty_evidence_fetch_status) as evidence_fetch_status,
  any_value(counterparty_evidence_reason_codes) as evidence_reason_codes,
  any_value(counterparty_evidence_coverage_scope) as evidence_coverage_scope,
  any_value(counterparty_evidence_coverage_start_block) as evidence_coverage_start_block,
  any_value(counterparty_evidence_coverage_end_block) as evidence_coverage_end_block,
  any_value(counterparty_evidence_schema_version) as evidence_schema_version,
  token_status,
  count(*) as transfer_count,
  count(*) filter (where direction = 'in') as inbound_transfer_count,
  count(*) filter (where direction = 'out') as outbound_transfer_count,
  count(distinct token_address) as token_count,
  min(block_timestamp) as first_seen_at,
  max(block_timestamp) as last_seen_at
from eligible_events
group by wallet_id, wallet_address, chain_id, counterparty_address, token_status
