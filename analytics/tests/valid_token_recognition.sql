select *
from {{ ref('int_token_enrichment') }}
where recognition_version != 'token-recognition-v1'
  or recognition_status not in ('recognized', 'other')
  or (
    metadata_source not in ('manual', 'ethereum_rpc')
    and recognition_status != 'recognized'
  )
  or (
    metadata_source = 'manual'
    and token_status = 'trusted'
    and recognition_status != 'recognized'
  )
  or (
    metadata_source = 'manual'
    and token_status = 'spam'
    and recognition_status != 'other'
  )
