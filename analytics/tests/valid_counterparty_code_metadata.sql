select address
from {{ ref('stg_counterparty_metadata') }}
where
  (fetch_status = 'complete' and address_type = 'wallet' and code_size_bytes != 0)
  or (fetch_status = 'complete' and address_type = 'contract' and coalesce(code_size_bytes, 0) <= 0)
  or (fetch_status = 'failed' and address_type != 'unknown')
