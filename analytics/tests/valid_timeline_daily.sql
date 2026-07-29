with events as (
  select
    *,
    cast(block_timestamp as date) as block_date
  from {{ ref('int_wallet_transfer_events') }}
),

expected as (
  select
    chain_id,
    wallet_address,
    block_date,
    token_address,
    coalesce(token_symbol, substr(token_address, 1, 10)) as token_symbol,
    recognition_status,
    counterparty_account_type,
    direction,
    count(*) as transfer_count
  from events
  group by
    chain_id,
    wallet_address,
    block_date,
    token_address,
    token_symbol,
    recognition_status,
    counterparty_account_type,
    direction
)

select
  coalesce(expected.chain_id, actual.chain_id) as chain_id,
  coalesce(expected.wallet_address, actual.wallet_address) as wallet_address,
  coalesce(expected.block_date, actual.block_date) as block_date,
  coalesce(expected.token_address, actual.token_address) as token_address
from expected
full outer join {{ ref('timeline_daily') }} as actual
  using (
    chain_id,
    wallet_address,
    block_date,
    token_address,
    token_symbol,
    recognition_status,
    counterparty_account_type,
    direction
  )
where expected.transfer_count is distinct from actual.transfer_count
