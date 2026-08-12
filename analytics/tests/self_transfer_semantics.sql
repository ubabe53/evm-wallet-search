with invalid_self_events as (
  select chain_id, transaction_hash, log_index
  from {{ ref('int_wallet_transfer_events') }}
  where (
    from_address = wallet_address
    and to_address = wallet_address
    and (
      direction is distinct from 'self'
      or counterparty_address is distinct from wallet_address
      or counterparty_account_type is distinct from 'unknown'
      or counterparty_evidence_fetch_status is distinct from 'not_fetched'
    )
  )
  or (
    direction = 'self'
    and (
      from_address is distinct from wallet_address
      or to_address is distinct from wallet_address
      or counterparty_address is distinct from wallet_address
    )
  )
)

select 'invalid_self_event' as failure
from invalid_self_events

{% if var('use_fixture', true) %}
union all

select 'missing_fixture_self_event' as failure
where not exists (
  select 1
  from {{ ref('int_wallet_transfer_events') }}
  where chain_id = 1
    and transaction_hash = '0x000000000000000000000000000000000000000000000000000000000a100013'
    and log_index = 1
    and direction = 'self'
)

union all

select 'fixture_token_summary_reconciliation' as failure
where not exists (
  select 1
  from {{ ref('token_summary') }}
  where token_address = '0x9999999999999999999999999999999999999999'
    and self_transfer_count = 5
    and transfer_count = inbound_transfer_count + outbound_transfer_count + self_transfer_count
)

union all

select 'fixture_timeline_direction' as failure
where not exists (
  select 1
  from {{ ref('timeline_daily') }}
  where direction = 'self'
    and token_address = '0x9999999999999999999999999999999999999999'
    and transfer_count = 1
)
{% endif %}
