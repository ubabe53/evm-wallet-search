select
  chain_id,
  wallet_address
from {{ ref('stg_wallets') }}
group by chain_id, wallet_address
having count(*) > 1
