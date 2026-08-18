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
{% if var('fixture_dataset', 'demo') == 'synthetic' %}
  select 'synthetic_fixture_exact_event_contract' as failure from fixture_profile where event_count != 100
  union all
  select 'synthetic_fixture_token_breadth' from fixture_profile where token_count < 5
  union all
  select 'synthetic_fixture_counterparty_breadth' from fixture_profile where counterparty_count < 8
  union all
  select 'synthetic_fixture_year_navigation' from fixture_profile where year_count < 5 or month_count < 10
  union all
  select 'synthetic_fixture_directions' from fixture_profile
  where inbound_count = 0 or outbound_count = 0 or self_count = 0
  union all
  select 'synthetic_fixture_directness' from fixture_profile
  where indirect_count = 0 or direct_count = 0 or unknown_directness_count = 0
  union all
  select 'synthetic_fixture_recognition_filters' from fixture_profile
  where recognized_count = 0 or other_count = 0
  union all
  select 'synthetic_fixture_account_evidence_must_be_empty'
  where exists (select 1 from {{ ref('stg_account_evidence') }})
  union all
  select 'synthetic_fixture_provenance'
  where not exists (
    select 1
    from {{ ref('pipeline_metadata') }}
    where data_source = 'fixture'
      and transfer_count = 100
      and snapshot_run_id is null
      and snapshot_start_block is null
      and snapshot_end_block is null
  )
{% else %}
  select 'mainnet_demo_exact_event_contract' as failure from fixture_profile
  where event_count != 90 or token_count != 9 or counterparty_count != 49
  union all
  select 'mainnet_demo_year_navigation' from fixture_profile
  where year_count != 3 or month_count < 10
  union all
  select 'mainnet_demo_directions' from fixture_profile
  where inbound_count = 0 or outbound_count = 0 or self_count != 0
  union all
  select 'mainnet_demo_recognition_filters' from fixture_profile
  where recognized_count = 0 or other_count = 0
  union all
  select 'mainnet_demo_account_evidence_incomplete'
  where (select count(*) from {{ ref('stg_account_evidence') }} where fetch_status = 'complete') != 49
  union all
  select 'mainnet_demo_provenance'
  where not exists (
    select 1
    from {{ ref('pipeline_metadata') }}
    where data_source = 'fixture'
      and configured_wallet_label = 'Gitcoin Schelling Point multisig'
      and wallet_address = '0x11c24f0031b4c35e2e9353764edc61299291e0af'
      and transfer_count = 90
      and snapshot_start_block = 0
      and snapshot_end_block = 25739543
      and snapshot_end_block_hash = '0x5374be585630353358d7c6a0b20106fc74c45577264cbe6a70ad8e4b0ed5f484'
      and snapshot_finality_policy = 'ethereum_finalized'
      and snapshot_source = 'envio_hyperindex'
      and snapshot_schema_version = 'mainnet-demo-snapshot-v1'
  )
{% endif %}
)

select * from failures
{% else %}
select 'fixture_test_disabled' as failure where false
{% endif %}
