select
  wallet_id,
  wallet_address,
  token_address,
  coalesce(token_symbol, substr(token_address, 1, 10)) as token_symbol,
  token_name,
  token_decimals,
  token_status,
  recognition_status,
  recognition_reason,
  recognition_source,
  recognition_version,
  metadata_source,
  metadata_source_url,
  token_label_reason,
  metadata_availability,
  token_quality,
  token_quality_sources,
  token_quality_source_count,
  token_quality_reason,
  token_quality_provenance,
  token_quality_version,
  token_reputation,
  token_reputation_score,
  token_reputation_reasons,
  token_reputation_version,
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
  ) as recipient_account_count,
  sum(cast(value_raw as bignum)) as value_raw_sum
from {{ ref('wallet_events') }}
group by wallet_id, wallet_address, token_address, token_symbol, token_name, token_decimals,
  token_status, recognition_status, recognition_reason, recognition_source, recognition_version,
  metadata_source, metadata_source_url, token_label_reason,
  metadata_availability, token_quality, token_quality_sources, token_quality_source_count,
  token_quality_reason, token_quality_provenance, token_quality_version,
  token_reputation, token_reputation_score, token_reputation_reasons, token_reputation_version,
  counterparty_account_type
