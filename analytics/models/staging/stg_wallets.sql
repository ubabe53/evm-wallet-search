{% if var('use_fixture', true) %}
select
  1 as chain_id,
  ens,
  lower(address) as wallet_address
{% if var('fixture_dataset', 'demo') == 'synthetic' %}
from {{ ref('wallets') }}
{% else %}
from {{ ref('wallets_demo') }}
{% endif %}
{% else %}
select
  chain_id,
  wallet_label as ens,
  lower(wallet_address) as wallet_address
from ops.wallet_targets
where lower(wallet_address) = lower('{{ env_var("EVM_WALLET_SCAN_ADDRESS") }}')
{% endif %}
