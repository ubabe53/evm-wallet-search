select
  chain_id,
  transaction_hash,
  log_index,
  count(*) as duplicate_count
from {{ ref('stg_erc20_transfers') }}
group by 1, 2, 3
having count(*) > 1
