select classified.transfer_id
from {{ ref('wallet_events') }} as classified
inner join {{ ref('int_wallet_transfer_events') }} as source using (transfer_id)
where (
    source.token_status = 'spam'
    and classified.token_status != 'spam'
  )
  or (
    source.token_status != 'spam'
    and classified.token_quality = 'high_confidence'
    and classified.token_status != 'trusted'
  )
  or (
    source.token_status != 'spam'
    and classified.token_quality != 'high_confidence'
    and classified.token_status != 'unverified'
  )
