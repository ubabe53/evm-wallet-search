with
{% if var('use_fixture', true) %}
wallets as (
  select chain_id, ens, wallet_address
  from {{ ref('stg_wallets') }}
),
{% else %}
wallets as (
  select
    chain_id,
    wallet_label as ens,
    lower(wallet_address) as wallet_address
  from ops.wallet_targets
),
{% endif %}

event_metrics as (
  select
    chain_id,
    wallet_address,
    count(*) as transfer_count,
    min(block_number) as event_block_number_min,
    max(block_number) as event_block_number_max,
    min(block_timestamp) as first_event_at,
    max(block_timestamp) as last_event_at
  from {{ ref('int_wallet_transfer_events') }}
  group by chain_id, wallet_address
),

account_evidence_population as (
  select
    chain_id,
    wallet_address,
    counterparty_address,
    count(*) as event_count,
    any_value(counterparty_evidence_fetch_status) as fetch_status,
    any_value(counterparty_observation_block_number) as observation_block_number,
    any_value(counterparty_observation_block_timestamp) as observation_block_timestamp,
    any_value(counterparty_evidence_schema_version) as evidence_schema_version
  from {{ ref('int_wallet_transfer_events') }}
  where counterparty_address != '0x0000000000000000000000000000000000000000'
    and counterparty_address != wallet_address
  group by chain_id, wallet_address, counterparty_address
),

account_evidence_metrics as (
  select
    chain_id,
    wallet_address,
    count(*) as account_evidence_eligible_address_count,
    count(*) filter (where fetch_status = 'complete') as account_evidence_classified_address_count,
    count(*) filter (where fetch_status = 'failed') as account_evidence_failed_address_count,
    count(*) filter (where fetch_status = 'not_fetched') as account_evidence_not_checked_address_count,
    sum(event_count) as account_evidence_eligible_event_count,
    coalesce(sum(event_count) filter (where fetch_status = 'complete'), 0) as account_evidence_classified_event_count,
    coalesce(sum(event_count) filter (where fetch_status = 'failed'), 0) as account_evidence_failed_event_count,
    coalesce(sum(event_count) filter (where fetch_status = 'not_fetched'), 0) as account_evidence_not_checked_event_count,
    min(observation_block_number) filter (where fetch_status = 'complete') as account_evidence_observation_block_number_min,
    max(observation_block_number) filter (where fetch_status = 'complete') as account_evidence_observation_block_number_max,
    min(cast(observation_block_timestamp as timestamptz)) filter (
      where fetch_status = 'complete'
    ) as account_evidence_observation_block_timestamp_min,
    max(cast(observation_block_timestamp as timestamptz)) filter (
      where fetch_status = 'complete'
    ) as account_evidence_observation_block_timestamp_max,
    any_value(evidence_schema_version) filter (where fetch_status = 'complete') as account_evidence_schema_version
  from account_evidence_population
  group by chain_id, wallet_address
)

{% if not var('use_fixture', true) %}, snapshot_runs as (
  select chain_id, wallet_address, run_id, generation_id, coverage_start_block, from_block, to_block, to_block_hash
  from (
    select chain_id, wallet_address, run_id, generation_id, from_block, to_block, to_block_hash,
      min(from_block) over (partition by chain_id, wallet_address) as coverage_start_block,
      row_number() over (
        partition by chain_id, wallet_address
        order by to_block desc, completed_at desc
      ) as wallet_run_rank
    from ops.pipeline_runs
    where chain_id = 1
      and scope_version = '{{ env_var("EVM_WALLET_SNAPSHOT_SCOPE_VERSION") }}'
      and (
        status = 'completed'
        or run_id = '{{ env_var("EVM_WALLET_SNAPSHOT_RUN_ID") }}'
      )
  )
  where wallet_run_rank = 1
)
{% endif %}

select
  coalesce(wallets.ens, wallets.wallet_address) as configured_wallet_label,
  wallets.wallet_address,
  wallets.chain_id,
  {% if var('use_fixture', true) %}'fixture'{% else %}'hyperindex'{% endif %} as data_source,
  current_timestamp as generated_at,
  {% if var('use_fixture', true) %}
  cast(null as varchar) as snapshot_run_id,
  cast(null as varchar) as snapshot_generation_id,
  cast(null as bigint) as snapshot_start_block,
  cast(null as bigint) as snapshot_end_block,
  cast(null as varchar) as snapshot_end_block_hash,
  cast(null as varchar) as snapshot_finality_policy,
  cast(null as varchar) as snapshot_scope_version,
  {% else %}
  snapshot_runs.run_id as snapshot_run_id,
  snapshot_runs.generation_id as snapshot_generation_id,
  snapshot_runs.coverage_start_block as snapshot_start_block,
  snapshot_runs.to_block as snapshot_end_block,
  snapshot_runs.to_block_hash as snapshot_end_block_hash,
  '{{ env_var("EVM_WALLET_SNAPSHOT_FINALITY_POLICY") }}' as snapshot_finality_policy,
  '{{ env_var("EVM_WALLET_SNAPSHOT_SCOPE_VERSION") }}' as snapshot_scope_version,
  {% endif %}
  coalesce(events.transfer_count, 0) as transfer_count,
  events.event_block_number_min,
  events.event_block_number_max,
  events.first_event_at,
  events.last_event_at,
  'distinct_nonzero_nonself_event_counterparties' as account_evidence_population_scope,
  coalesce(evidence.account_evidence_eligible_address_count, 0) as account_evidence_eligible_address_count,
  coalesce(evidence.account_evidence_classified_address_count, 0) as account_evidence_classified_address_count,
  coalesce(evidence.account_evidence_failed_address_count, 0) as account_evidence_failed_address_count,
  coalesce(evidence.account_evidence_not_checked_address_count, 0) as account_evidence_not_checked_address_count,
  coalesce(evidence.account_evidence_eligible_event_count, 0) as account_evidence_eligible_event_count,
  coalesce(evidence.account_evidence_classified_event_count, 0) as account_evidence_classified_event_count,
  coalesce(evidence.account_evidence_failed_event_count, 0) as account_evidence_failed_event_count,
  coalesce(evidence.account_evidence_not_checked_event_count, 0) as account_evidence_not_checked_event_count,
  evidence.account_evidence_observation_block_number_min,
  evidence.account_evidence_observation_block_number_max,
  evidence.account_evidence_observation_block_timestamp_min,
  evidence.account_evidence_observation_block_timestamp_max,
  evidence.account_evidence_schema_version
from wallets
left join event_metrics as events using (chain_id, wallet_address)
left join account_evidence_metrics as evidence using (chain_id, wallet_address)
{% if not var('use_fixture', true) %}
join snapshot_runs using (chain_id, wallet_address)
{% endif %}
