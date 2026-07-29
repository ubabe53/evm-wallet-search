select
  events.* exclude (token_status),
  case
    when events.token_status = 'spam' then 'spam'
    when events.token_quality = 'high_confidence' then 'trusted'
    else 'unverified'
  end as token_status
from {{ ref('int_wallet_transfer_events') }} as events
