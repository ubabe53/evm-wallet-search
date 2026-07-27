select
  'wallet:' || wallet_address as node_id,
  'wallet' as node_type,
  coalesce(ens, wallet_address) as label,
  wallet_address as address,
  cast(null as varchar) as token_address,
  cast(null as varchar) as symbol,
  cast(null as varchar) as account_type,
  cast(null as varchar) as code_state,
  cast(null as bigint) as observation_block_number,
  cast(null as varchar) as observation_block_timestamp,
  cast(null as varchar) as eip7702_delegation_target,
  cast(null as varchar) as evidence_fetch_status,
  cast(null as varchar) as evidence_reason_codes
from {{ ref('wallet_events') }}
where direction != 'self'
group by wallet_address, ens

union all

select
  'counterparty:' || counterparty_address as node_id,
  'counterparty' as node_type,
  counterparty_address as label,
  counterparty_address as address,
  cast(null as varchar) as token_address,
  cast(null as varchar) as symbol,
  any_value(counterparty_account_type) as account_type,
  any_value(counterparty_code_state) as code_state,
  any_value(counterparty_observation_block_number) as observation_block_number,
  any_value(counterparty_observation_block_timestamp) as observation_block_timestamp,
  any_value(counterparty_eip7702_delegation_target) as eip7702_delegation_target,
  any_value(counterparty_evidence_fetch_status) as evidence_fetch_status,
  any_value(counterparty_evidence_reason_codes) as evidence_reason_codes
from {{ ref('wallet_events') }}
where direction != 'self'
group by counterparty_address

union all

select
  'token:' || token_address as node_id,
  'token' as node_type,
  coalesce(token_symbol, substr(token_address, 1, 10)) as label,
  cast(null as varchar) as address,
  token_address,
  token_symbol as symbol,
  cast(null as varchar) as account_type,
  cast(null as varchar) as code_state,
  cast(null as bigint) as observation_block_number,
  cast(null as varchar) as observation_block_timestamp,
  cast(null as varchar) as eip7702_delegation_target,
  cast(null as varchar) as evidence_fetch_status,
  cast(null as varchar) as evidence_reason_codes
from {{ ref('wallet_events') }}
where direction != 'self'
group by token_address, token_symbol
