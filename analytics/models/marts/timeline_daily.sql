select
  wallet_id,
  wallet_address,
  block_date,
  token_address,
  coalesce(token_symbol, substr(token_address, 1, 10)) as token_symbol,
  token_status,
  metadata_source,
  metadata_source_url,
  token_reputation,
  token_reputation_score,
  token_reputation_reasons,
  interaction_legitimacy,
  interaction_legitimacy_score,
  interaction_legitimacy_reasons,
  direction,
  count(*) as transfer_count,
  case
    when count(amount_decimal) = count(*) then sum(amount_decimal)
    else null
  end as amount_decimal_sum,
  sum(cast(value_raw as bignum)) as value_raw_sum
from {{ ref('wallet_events') }}
group by wallet_id, wallet_address, block_date, token_address, token_symbol,
  token_status, metadata_source, metadata_source_url, token_reputation,
  token_reputation_score, token_reputation_reasons, interaction_legitimacy,
  interaction_legitimacy_score, interaction_legitimacy_reasons, direction
