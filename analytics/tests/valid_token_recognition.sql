select *
from {{ ref('int_token_enrichment') }}
where recognition_version != 'token-recognition-v1'
  or recognition_status not in ('recognized', 'other')
  or (
    metadata_source not in ('manual', 'ethereum_rpc')
    and recognition_status != 'recognized'
  )
  or (
    recognition_source = 'manual'
    and recognition_reason not in ('reviewed_manual_recognized', 'reviewed_manual_other')
  )
