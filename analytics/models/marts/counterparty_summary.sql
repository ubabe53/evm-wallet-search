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
  counterparty_address,
  counterparty_type,
  token_status,
  count(*) as transfer_count,
  count(*) filter (where direction = 'in') as inbound_transfer_count,
  count(*) filter (where direction = 'out') as outbound_transfer_count,
  count(distinct token_address) as token_count,
  min(block_timestamp) as first_seen_at,
  max(block_timestamp) as last_seen_at
from eligible_events
group by wallet_id, wallet_address, counterparty_address, counterparty_type, token_status
