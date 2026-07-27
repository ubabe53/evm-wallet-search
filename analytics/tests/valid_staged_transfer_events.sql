select
  chain_id,
  transaction_hash,
  log_index
from {{ ref('stg_transfer_events') }}
where not regexp_matches(block_hash, '^0x[0-9a-f]{64}$')
  or not regexp_matches(value_raw, '^(0|[1-9][0-9]*)$')
