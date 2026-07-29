select
  chain_id,
  wallet_address,
  transaction_hash,
  log_index,
  count(*) as duplicate_count
from {{ ref('int_wallet_transfer_events') }}
group by chain_id, wallet_address, transaction_hash, log_index
having count(*) > 1
