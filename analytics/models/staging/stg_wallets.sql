select
  1 as chain_id,
  ens,
  lower(address) as wallet_address,
  label
from {{ ref('wallets') }}
