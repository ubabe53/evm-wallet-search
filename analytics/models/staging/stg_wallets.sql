select
  1 as chain_id,
  ens,
  lower(address) as wallet_address
from {{ ref('wallets') }}
{% if not var('use_fixture', true) %}
where lower(address) = lower('{{ env_var("EVM_WALLET_SCAN_ADDRESS") }}')
{% endif %}
