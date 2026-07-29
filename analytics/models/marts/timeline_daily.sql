select
  chain_id,
  wallet_address,
  block_date,
  token_address,
  coalesce(token_symbol, substr(token_address, 1, 10)) as token_symbol,
  recognition_status,
  recognition_reason,
  recognition_source,
  recognition_version,
  metadata_availability,
  metadata_source,
  metadata_source_url,
  counterparty_account_type,
  direction,
  count(*) as transfer_count,
  sum(cast(value_raw as bignum)) as value_raw_sum
from {{ ref('int_wallet_transfer_events') }}
group by chain_id, wallet_address, block_date, token_address, token_symbol,
  recognition_status, recognition_reason, recognition_source, recognition_version,
  metadata_availability, metadata_source, metadata_source_url,
  counterparty_account_type, direction
