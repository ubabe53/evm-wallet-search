select
  wallet_id,
  ens,
  lower(address) as wallet_address,
  label
from {{ ref('wallets') }}
