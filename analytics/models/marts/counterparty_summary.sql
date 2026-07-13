select
  wallet_id,
  wallet_address,
  counterparty_address,
  counterparty_type,
  direction,
  count(*) as transfer_count,
  count(distinct token_address) as token_count,
  min(block_timestamp) as first_seen_at,
  max(block_timestamp) as last_seen_at
from {{ ref('wallet_events') }}
group by wallet_id, wallet_address, counterparty_address, counterparty_type, direction
