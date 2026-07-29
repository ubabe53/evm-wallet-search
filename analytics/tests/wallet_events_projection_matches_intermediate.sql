select
  coalesce(events.chain_id, semantic.chain_id) as chain_id,
  coalesce(events.wallet_address, semantic.wallet_address) as wallet_address,
  coalesce(events.transaction_hash, semantic.transaction_hash) as transaction_hash,
  coalesce(events.log_index, semantic.log_index) as log_index
from {{ ref('wallet_events') }} as events
full outer join {{ ref('int_wallet_transfer_events') }} as semantic
  using (chain_id, wallet_address, transaction_hash, log_index)
where events.chain_id is null
  or semantic.chain_id is null
  or events.block_number is distinct from semantic.block_number
  or events.block_timestamp is distinct from semantic.block_timestamp
  or events.transaction_index is distinct from semantic.transaction_index
  or events.token_address is distinct from semantic.token_address
  or events.token_symbol is distinct from semantic.token_symbol
  or events.token_name is distinct from semantic.token_name
  or events.recognition_status is distinct from semantic.recognition_status
  or events.direction is distinct from semantic.direction
  or events.is_indirect is distinct from semantic.is_indirect
  or events.counterparty_address is distinct from semantic.counterparty_address
  or events.counterparty_account_type is distinct from semantic.counterparty_account_type
  or events.counterparty_code_state is distinct from semantic.counterparty_code_state
  or events.counterparty_observation_block_number
    is distinct from semantic.counterparty_observation_block_number
  or events.counterparty_eip7702_delegation_target
    is distinct from semantic.counterparty_eip7702_delegation_target
