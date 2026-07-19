select
  events.transfer_id
from {{ ref('wallet_events') }} as events
inner join {{ ref('stg_erc20_transfers') }} as source using (transfer_id)
where events.chain_id != source.chain_id
  or events.block_number != source.block_number
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
