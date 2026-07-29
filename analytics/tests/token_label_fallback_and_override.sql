select transfer_id
from {{ ref('wallet_events') }}
where
  (token_address = '0x9999999999999999999999999999999999999999'
    and (token_status != 'unverified' or metadata_source != 'ethereum_rpc'
      or metadata_availability != 'complete' or token_quality != 'unknown'
      or token_quality_source_count != 0 or token_quality_reason != 'rpc_metadata_only'
      or token_quality_version != 'token-quality-v1'
      or token_name != 'Claim at visticlaim.com' or token_symbol != 'VISTI.COM'
      or token_decimals != 6
      or value_raw != '115792089237316195423570985008687907853269984665640564039457584007913129639935'))
  or
  (token_address = '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48'
    and (token_status != 'trusted' or metadata_source != 'manual'
      or token_quality != 'high_confidence' or token_quality_reason != 'reviewed_manual_approval'))
