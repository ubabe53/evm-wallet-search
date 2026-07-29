with semantic_events as (
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

delivery_events as (
  select
    chain_id,
    wallet_address,
    count(*) as transfer_count
  from {{ ref('wallet_events') }}
  group by chain_id, wallet_address
)

select metadata.chain_id, metadata.wallet_address
from {{ ref('pipeline_metadata') }} as metadata
left join semantic_events using (chain_id, wallet_address)
left join delivery_events using (chain_id, wallet_address)
where metadata.transfer_count != coalesce(semantic_events.transfer_count, 0)
  or metadata.transfer_count != coalesce(delivery_events.transfer_count, 0)
  or metadata.event_block_number_min is distinct from semantic_events.event_block_number_min
  or metadata.event_block_number_max is distinct from semantic_events.event_block_number_max
  or metadata.first_event_at is distinct from semantic_events.first_event_at
  or metadata.last_event_at is distinct from semantic_events.last_event_at
  or (
    metadata.transfer_count = 0
    and (
      metadata.event_block_number_min is not null
      or metadata.event_block_number_max is not null
      or metadata.first_event_at is not null
      or metadata.last_event_at is not null
    )
  )
  or (
    metadata.transfer_count > 0
    and (
      metadata.event_block_number_min is null
      or metadata.event_block_number_max is null
      or metadata.first_event_at is null
      or metadata.last_event_at is null
      or metadata.event_block_number_min > metadata.event_block_number_max
      or metadata.first_event_at > metadata.last_event_at
    )
  )
  or (
    metadata.data_source = 'hyperindex'
    and metadata.transfer_count > 0
    and (
      metadata.event_block_number_min < metadata.snapshot_start_block
      or metadata.event_block_number_max > metadata.snapshot_end_block
    )
  )
