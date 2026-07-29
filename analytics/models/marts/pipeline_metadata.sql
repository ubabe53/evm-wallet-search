with event_metrics as (
  select
    chain_id,
    wallet_address,
    count(*) as transfer_count,
    count(distinct token_address) as token_count,
    count(distinct counterparty_address) filter (
      where counterparty_address != wallet_address
    ) as counterparty_count,
    count(*) filter (where recognition_status = 'recognized') as recognized_transfer_count,
    count(distinct token_address) filter (where recognition_status = 'recognized') as recognized_token_count,
    count(*) filter (where recognition_status = 'other') as other_transfer_count,
    count(distinct token_address) filter (where recognition_status = 'other') as other_token_count,
    min(block_timestamp) as first_event_at,
    max(block_timestamp) as last_event_at
  from {{ ref('wallet_events') }}
  group by chain_id, wallet_address
),

interaction_metrics as (
  select chain_id, wallet_address, count(*) as interaction_count
  from (
    select distinct chain_id, wallet_address, counterparty_address, token_address, direction
    from {{ ref('wallet_events') }}
    where direction != 'self'
  )
  group by chain_id, wallet_address
),

timeline_metrics as (
  select chain_id, wallet_address, count(*) as timeline_row_count
  from {{ ref('timeline_daily') }}
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
  from {{ ref('wallet_events') }}
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
    case
      when count(*) = 0 then null
      else count(*) filter (where fetch_status = 'complete')::double / count(*)
    end as account_evidence_address_coverage_rate,
    sum(event_count) as account_evidence_eligible_event_count,
    coalesce(sum(event_count) filter (where fetch_status = 'complete'), 0) as account_evidence_classified_event_count,
    coalesce(sum(event_count) filter (where fetch_status = 'failed'), 0) as account_evidence_failed_event_count,
    coalesce(sum(event_count) filter (where fetch_status = 'not_fetched'), 0) as account_evidence_not_checked_event_count,
    case
      when sum(event_count) = 0 then null
      else coalesce(sum(event_count) filter (where fetch_status = 'complete'), 0)::double / sum(event_count)
    end as account_evidence_event_coverage_rate,
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

select
  wallets.ens,
  wallets.wallet_address,
  wallets.chain_id,
  {% if var('use_fixture', true) %}'fixture'{% else %}'hyperindex'{% endif %} as data_source,
  current_timestamp as generated_at,
  {% if var('use_fixture', true) %}
  cast(null as varchar) as snapshot_run_id,
  cast(null as bigint) as snapshot_start_block,
  cast(null as bigint) as snapshot_increment_start_block,
  cast(null as bigint) as snapshot_end_block,
  cast(null as varchar) as snapshot_end_block_hash,
  cast(null as varchar) as snapshot_finality_policy,
  cast(null as varchar) as snapshot_scope_version,
  {% else %}
  '{{ env_var("EVM_WALLET_SNAPSHOT_RUN_ID") }}' as snapshot_run_id,
  cast({{ env_var("EVM_WALLET_SNAPSHOT_START_BLOCK") }} as bigint) as snapshot_start_block,
  cast({{ env_var("EVM_WALLET_SNAPSHOT_INCREMENT_START_BLOCK") }} as bigint) as snapshot_increment_start_block,
  cast({{ env_var("EVM_WALLET_SNAPSHOT_END_BLOCK") }} as bigint) as snapshot_end_block,
  '{{ env_var("EVM_WALLET_SNAPSHOT_END_BLOCK_HASH") }}' as snapshot_end_block_hash,
  '{{ env_var("EVM_WALLET_SNAPSHOT_FINALITY_POLICY") }}' as snapshot_finality_policy,
  '{{ env_var("EVM_WALLET_SNAPSHOT_SCOPE_VERSION") }}' as snapshot_scope_version,
  {% endif %}
  coalesce(events.transfer_count, 0) as transfer_count,
  coalesce(events.token_count, 0) as token_count,
  coalesce(events.counterparty_count, 0) as counterparty_count,
  coalesce(events.recognized_transfer_count, 0) as recognized_transfer_count,
  coalesce(events.recognized_token_count, 0) as recognized_token_count,
  coalesce(events.other_transfer_count, 0) as other_transfer_count,
  coalesce(events.other_token_count, 0) as other_token_count,
  coalesce(interactions.interaction_count, 0) as interaction_count,
  coalesce(timeline.timeline_row_count, 0) as timeline_row_count,
  'distinct_nonzero_nonself_event_counterparties' as account_evidence_population_scope,
  coalesce(evidence.account_evidence_eligible_address_count, 0) as account_evidence_eligible_address_count,
  coalesce(evidence.account_evidence_classified_address_count, 0) as account_evidence_classified_address_count,
  coalesce(evidence.account_evidence_failed_address_count, 0) as account_evidence_failed_address_count,
  coalesce(evidence.account_evidence_not_checked_address_count, 0) as account_evidence_not_checked_address_count,
  evidence.account_evidence_address_coverage_rate,
  coalesce(evidence.account_evidence_eligible_event_count, 0) as account_evidence_eligible_event_count,
  coalesce(evidence.account_evidence_classified_event_count, 0) as account_evidence_classified_event_count,
  coalesce(evidence.account_evidence_failed_event_count, 0) as account_evidence_failed_event_count,
  coalesce(evidence.account_evidence_not_checked_event_count, 0) as account_evidence_not_checked_event_count,
  evidence.account_evidence_event_coverage_rate,
  evidence.account_evidence_observation_block_number_min,
  evidence.account_evidence_observation_block_number_max,
  evidence.account_evidence_observation_block_timestamp_min,
  evidence.account_evidence_observation_block_timestamp_max,
  evidence.account_evidence_schema_version,
  events.first_event_at,
  events.last_event_at
from {{ ref('stg_wallets') }} as wallets
left join event_metrics as events using (chain_id, wallet_address)
left join interaction_metrics as interactions using (chain_id, wallet_address)
left join timeline_metrics as timeline using (chain_id, wallet_address)
left join account_evidence_metrics as evidence using (chain_id, wallet_address)
