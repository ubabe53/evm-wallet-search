select
  'wallet:' || wallet_address as node_id,
  'wallet' as node_type,
  coalesce(ens, wallet_address) as label,
  wallet_address as address,
  null as token_address,
  null as symbol,
  'wallet' as address_type
from {{ ref('wallet_events') }}
group by wallet_address, ens

union all

select
  'counterparty:' || counterparty_address as node_id,
  'counterparty' as node_type,
  counterparty_address as label,
  counterparty_address as address,
  null as token_address,
  null as symbol,
  counterparty_type as address_type
from {{ ref('wallet_events') }}
group by counterparty_address, counterparty_type

union all

select
  'token:' || token_address as node_id,
  'token' as node_type,
  coalesce(token_symbol, substr(token_address, 1, 10)) as label,
  null as address,
  token_address,
  token_symbol as symbol,
  null as address_type
from {{ ref('wallet_events') }}
group by token_address, token_symbol
