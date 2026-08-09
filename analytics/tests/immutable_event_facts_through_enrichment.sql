with expected as (
  select source.*, wallets.wallet_address
  from {{ ref('stg_transfer_events') }} as source
  join {{ ref('stg_wallets') }} as wallets
    on source.chain_id = wallets.chain_id
    and (
      source.from_address = wallets.wallet_address
      or source.to_address = wallets.wallet_address
    )
),

current_events as (
  select events.*
  from {{ ref('int_wallet_transfer_events') }} as events
  {% if not var('use_fixture', true) %}
  join {{ ref('stg_wallets') }} as wallets using (chain_id, wallet_address)
  where events.block_number between {{ env_var("EVM_WALLET_SNAPSHOT_START_BLOCK") }}
    and {{ env_var("EVM_WALLET_SNAPSHOT_END_BLOCK") }}
  {% endif %}
)

select
  coalesce(events.chain_id, source.chain_id) as chain_id,
  coalesce(events.wallet_address, source.wallet_address) as wallet_address,
  coalesce(events.transaction_hash, source.transaction_hash) as transaction_hash,
  coalesce(events.log_index, source.log_index) as log_index
from current_events as events
full outer join expected as source
  using (chain_id, wallet_address, transaction_hash, log_index)
where events.chain_id is null
  or source.chain_id is null
  or events.wallet_address is distinct from source.wallet_address
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
