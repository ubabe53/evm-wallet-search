select *
from {{ ref('pipeline_metadata') }}
where
  (
    data_source = 'fixture'
    {% if var('fixture_dataset', 'demo') == 'synthetic' %}
    and (
      snapshot_run_id is not null
      or snapshot_start_block is not null
      or snapshot_end_block is not null
      or snapshot_end_block_hash is not null
      or snapshot_finality_policy is not null
      or snapshot_scope_version is not null
      or snapshot_source is not null
      or snapshot_schema_version is not null
      or wallet_attribution_source_url is not null
    )
    {% else %}
    and (
      snapshot_run_id is null
      or snapshot_generation_id is null
      or snapshot_start_block is null
      or snapshot_end_block is null
      or snapshot_end_block_hash is null
      or snapshot_finality_policy != 'ethereum_finalized'
      or snapshot_scope_version is null
      or snapshot_source != 'envio_hyperindex'
      or snapshot_schema_version is null
      or wallet_attribution_source_url is null
      or snapshot_start_block > snapshot_end_block
      or not regexp_matches(snapshot_end_block_hash, '^0x[0-9a-f]{64}$')
    )
    {% endif %}
  )
  or (
    data_source = 'hyperindex'
    and (
      snapshot_run_id is null
      or snapshot_start_block is null
      or snapshot_end_block is null
      or snapshot_end_block_hash is null
      or snapshot_finality_policy != 'ethereum_finalized'
      or snapshot_scope_version is null
      or snapshot_source != 'envio_hyperindex'
      or snapshot_start_block > snapshot_end_block
      or not regexp_matches(snapshot_end_block_hash, '^0x[0-9a-f]{64}$')
    )
  )
