{% if var('use_fixture', true) %}
with fixture_profile as (
  select
    count(*) as event_count,
    count(distinct token_address) as token_count,
    count(distinct counterparty_address) filter (
      where counterparty_address != wallet_address
    ) as counterparty_count,
    count(distinct extract(year from block_timestamp)) as year_count,
    count(distinct date_trunc('month', block_timestamp)) as month_count,
    count(*) filter (where direction = 'in') as inbound_count,
    count(*) filter (where direction = 'out') as outbound_count,
    count(*) filter (where direction = 'self') as self_count,
    count(*) filter (where is_indirect) as indirect_count,
    count(*) filter (where not is_indirect) as direct_count,
    count(*) filter (where is_indirect is null) as unknown_directness_count,
    count(*) filter (where recognition_status = 'recognized') as recognized_count,
    count(*) filter (where recognition_status = 'other') as other_count
  from {{ ref('wallet_events') }}
),
failures as (
  select 'fixture_exact_event_contract' as failure from fixture_profile where event_count != 100
  union all
  select 'fixture_token_breadth' from fixture_profile where token_count < 5
  union all
  select 'fixture_counterparty_breadth' from fixture_profile where counterparty_count < 8
  union all
  select 'fixture_year_navigation' from fixture_profile where year_count < 5 or month_count < 10
  union all
  select 'fixture_directions' from fixture_profile
  where inbound_count = 0 or outbound_count = 0 or self_count = 0
  union all
  select 'fixture_directness' from fixture_profile
  where indirect_count = 0 or direct_count = 0 or unknown_directness_count = 0
  union all
  select 'fixture_recognition_filters' from fixture_profile
  where recognized_count = 0 or other_count = 0
  union all
  select 'fixture_account_evidence_must_be_empty'
  where exists (select 1 from {{ ref('stg_account_evidence') }})
  union all
  select 'fixture_provenance'
  where not exists (
    select 1
    from {{ ref('pipeline_metadata') }}
    where data_source = 'fixture'
      and transfer_count = 100
      and snapshot_run_id is null
      and snapshot_start_block is null
      and snapshot_end_block is null
      and snapshot_end_block_hash is null
      and snapshot_finality_policy is null
      and snapshot_scope_version is null
  )
)

select * from failures
{% else %}
select 'fixture_test_disabled' as failure where false
{% endif %}
