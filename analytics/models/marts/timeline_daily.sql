select
  chain_id,
  wallet_address,
  block_date,
  token_address,
  coalesce(token_symbol, substr(token_address, 1, 10)) as token_symbol,
  recognition_status,
  counterparty_account_type,
  direction,
  count(*) as transfer_count
from {{ ref('int_wallet_transfer_events') }}
group by chain_id, wallet_address, block_date, token_address, token_symbol,
  recognition_status, counterparty_account_type, direction
