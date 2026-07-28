select
  chain_id,
  wallet_address
from {{ ref('pipeline_metadata') }}
group by chain_id, wallet_address
having count(*) > 1
