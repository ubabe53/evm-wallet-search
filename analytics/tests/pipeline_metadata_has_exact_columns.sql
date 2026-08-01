-- depends_on: {{ ref('pipeline_metadata') }}

with expected(column_name) as (
  values
    ('configured_wallet_label'),
    ('wallet_address'),
    ('chain_id'),
    ('data_source'),
    ('generated_at'),
    ('snapshot_run_id'),
    ('snapshot_generation_id'),
    ('snapshot_start_block'),
    ('snapshot_end_block'),
    ('snapshot_end_block_hash'),
    ('snapshot_finality_policy'),
    ('snapshot_scope_version'),
    ('transfer_count'),
    ('event_block_number_min'),
    ('event_block_number_max'),
    ('first_event_at'),
    ('last_event_at'),
    ('account_evidence_population_scope'),
    ('account_evidence_eligible_address_count'),
    ('account_evidence_classified_address_count'),
    ('account_evidence_failed_address_count'),
    ('account_evidence_not_checked_address_count'),
    ('account_evidence_eligible_event_count'),
    ('account_evidence_classified_event_count'),
    ('account_evidence_failed_event_count'),
    ('account_evidence_not_checked_event_count'),
    ('account_evidence_observation_block_number_min'),
    ('account_evidence_observation_block_number_max'),
    ('account_evidence_observation_block_timestamp_min'),
    ('account_evidence_observation_block_timestamp_max'),
    ('account_evidence_schema_version')
),

actual as (
  select column_name
  from information_schema.columns
  where table_schema = '{{ target.schema }}'
    and table_name = 'pipeline_metadata'
)

select 'missing' as issue, expected.column_name
from expected
left join actual using (column_name)
where actual.column_name is null

union all

select 'unexpected' as issue, actual.column_name
from actual
left join expected using (column_name)
where expected.column_name is null
