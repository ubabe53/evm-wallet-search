select transfer_id
from {{ ref('wallet_events') }}
where
  (token_address = '0x9999999999999999999999999999999999999999'
    and (token_status != 'suspected_spam' or token_reputation != 'suspected_spam'
      or token_reputation_score < 60 or metadata_source != 'ethereum_rpc'
      or metadata_availability != 'complete' or token_quality != 'unknown'
      or token_quality_source_count != 0 or token_quality_reason != 'rpc_metadata_only'
      or token_quality_version != 'token-quality-v1'
      or token_name != 'Claim at visticlaim.com' or token_symbol != 'VISTI.COM'
      or token_decimals != 6 or amount_decimal != 500000))
  or
  (token_address = '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48'
    and (token_status != 'trusted' or metadata_source != 'manual'
      or token_quality != 'high_confidence' or token_quality_reason != 'reviewed_manual_approval'))
