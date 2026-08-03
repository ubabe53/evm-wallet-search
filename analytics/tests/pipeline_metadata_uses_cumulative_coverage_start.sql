{% if var('use_fixture', true) %}
select cast(null as integer) as chain_id
where false
{% else %}
with expected_coverage as (
  select
    chain_id,
    lower(wallet_address) as wallet_address,
    min(from_block) as coverage_start_block
  from ops.pipeline_runs
  where chain_id = 1
    and (
      status = 'completed'
      or run_id = '{{ env_var("EVM_WALLET_SNAPSHOT_RUN_ID") }}'
    )
    and scope_version = '{{ env_var("EVM_WALLET_SNAPSHOT_SCOPE_VERSION") }}'
  group by chain_id, lower(wallet_address)
)

select metadata.chain_id, metadata.wallet_address
from {{ ref('pipeline_metadata') }} as metadata
join expected_coverage using (chain_id, wallet_address)
where metadata.snapshot_start_block is distinct from expected_coverage.coverage_start_block
{% endif %}
