select
  wallet_id,
  wallet_address,
  token_address,
  coalesce(token_symbol, substr(token_address, 1, 10)) as token_symbol,
  token_name,
  token_decimals,
  token_status,
  metadata_source,
  metadata_source_url,
  token_label_reason,
  token_reputation,
  token_reputation_score,
  token_reputation_reasons,
  count(*) as transfer_count,
  count(*) filter (where direction = 'in') as inbound_transfer_count,
  count(*) filter (where direction = 'out') as outbound_transfer_count,
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
  ) as recipient_account_count,
  case
    when token_decimals is null then null
    else sum(amount_decimal)
  end as amount_decimal_sum,
  sum(cast(value_raw as bignum)) as value_raw_sum
from {{ ref('wallet_events') }}
group by wallet_id, wallet_address, token_address, token_symbol, token_name, token_decimals,
  token_status, metadata_source, metadata_source_url, token_label_reason,
  token_reputation, token_reputation_score, token_reputation_reasons
