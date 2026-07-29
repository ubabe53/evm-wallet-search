select
  coalesce(events.chain_id, source.chain_id) as chain_id,
  coalesce(events.transaction_hash, source.transaction_hash) as transaction_hash,
  coalesce(events.log_index, source.log_index) as log_index
from {{ ref('int_wallet_transfer_events') }} as events
full outer join {{ ref('stg_transfer_events') }} as source
  using (chain_id, transaction_hash, log_index)
where events.chain_id is null
  or source.chain_id is null
  or events.chain_id != source.chain_id
  or events.block_number != source.block_number
  or events.block_hash != source.block_hash
  or events.block_timestamp != source.block_timestamp
  or events.transaction_hash != source.transaction_hash
  or events.transaction_index != source.transaction_index
  or events.transaction_from_address is distinct from source.transaction_from_address
  or events.transaction_to_address is distinct from source.transaction_to_address
  or events.log_index != source.log_index
  or events.token_address != source.token_address
  or events.from_address != source.from_address
  or events.to_address != source.to_address
  or events.value_raw != source.value_raw
