select
  chain_id,
  wallet_address,
  token_address,
  coalesce(token_symbol, substr(token_address, 1, 10)) as token_symbol,
  token_name,
  recognition_status,
  counterparty_account_type,
  count(*) as transfer_count,
  count(*) filter (where direction = 'in') as inbound_transfer_count,
  count(*) filter (where direction = 'out') as outbound_transfer_count,
  count(*) filter (where direction = 'self') as self_transfer_count,
  count(*) filter (where direction = 'in' and is_indirect) as indirect_inbound_transfer_count,
  count(*) filter (where direction = 'out' and is_indirect) as indirect_outbound_transfer_count,
  count(distinct counterparty_address) filter (
    where counterparty_address != '0x0000000000000000000000000000000000000000'
      and counterparty_address != wallet_address
  ) as counterparty_count,
  count(distinct counterparty_address) filter (
    where direction = 'in'
      and counterparty_address != '0x0000000000000000000000000000000000000000'
      and counterparty_address != wallet_address
  ) as sender_account_count,
  count(distinct counterparty_address) filter (
    where direction = 'out'
      and counterparty_address != '0x0000000000000000000000000000000000000000'
      and counterparty_address != wallet_address
  ) as recipient_account_count
from {{ ref('int_wallet_transfer_events') }}
group by chain_id, wallet_address, token_address, token_symbol, token_name,
  recognition_status, counterparty_account_type
