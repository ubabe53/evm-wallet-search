with token_contracts as (
  select distinct chain_id, token_address
  from {{ ref('wallet_events') }}
),
eligible_events as (
  select events.*
  from {{ ref('wallet_events') }} as events
  left join token_contracts
    on events.chain_id = token_contracts.chain_id
    and events.counterparty_address = token_contracts.token_address
  where events.counterparty_address != '0x0000000000000000000000000000000000000000'
    and events.counterparty_address != events.wallet_address
    and token_contracts.token_address is null
)
select
  chain_id,
  wallet_address,
  counterparty_address,
  any_value(counterparty_account_type) as account_type,
  any_value(counterparty_code_state) as code_state,
  any_value(counterparty_code_size_bytes) as code_size_bytes,
  any_value(counterparty_observation_block_number) as observation_block_number,
  any_value(counterparty_observation_block_timestamp) as observation_block_timestamp,
  any_value(counterparty_eip7702_delegation_target) as eip7702_delegation_target,
  any_value(counterparty_evidence_fetch_status) as evidence_fetch_status,
  any_value(counterparty_evidence_reason_codes) as evidence_reason_codes,
  any_value(counterparty_evidence_schema_version) as evidence_schema_version,
  recognition_status,
  count(*) as transfer_count,
  count(*) filter (where direction = 'in') as inbound_transfer_count,
  count(*) filter (where direction = 'out') as outbound_transfer_count,
  count(distinct token_address) as token_count,
  min(block_timestamp) as first_seen_at,
  max(block_timestamp) as last_seen_at
from eligible_events
group by chain_id, wallet_address, counterparty_address, recognition_status
