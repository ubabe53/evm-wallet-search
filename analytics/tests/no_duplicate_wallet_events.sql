select
  chain_id,
  wallet_address,
  transaction_hash,
  log_index,
  count(*) as row_count
from {{ ref('wallet_events') }}
group by chain_id, wallet_address, transaction_hash, log_index
having count(*) > 1
