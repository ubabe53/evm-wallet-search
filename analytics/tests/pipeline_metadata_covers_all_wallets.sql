with expected_wallets as (
  {% if var('use_fixture', true) %}
  select chain_id, wallet_address
  from {{ ref('stg_wallets') }}
  {% else %}
  select targets.chain_id, lower(targets.wallet_address) as wallet_address
  from ops.wallet_targets as targets
  join (
    select distinct chain_id, lower(wallet_address) as wallet_address
    from ops.pipeline_runs
    where status = 'completed'
      and scope_version = '{{ env_var("EVM_WALLET_SNAPSHOT_SCOPE_VERSION") }}'
  ) as scanned using (chain_id, wallet_address)
  {% endif %}
),
actual_wallets as (
  select chain_id, wallet_address
  from {{ ref('pipeline_metadata') }}
)

select expected.chain_id, expected.wallet_address
from expected_wallets as expected
left join actual_wallets as actual using (chain_id, wallet_address)
where actual.wallet_address is null

union all

select actual.chain_id, actual.wallet_address
from actual_wallets as actual
left join expected_wallets as expected using (chain_id, wallet_address)
where expected.wallet_address is null
