select summaries.*
from {{ ref('counterparty_summary') }} as summaries
where summaries.transfer_count != summaries.inbound_transfer_count + summaries.outbound_transfer_count
  or summaries.counterparty_address = '0x0000000000000000000000000000000000000000'
  or summaries.counterparty_address = summaries.wallet_address
  or exists (
    select 1
    from {{ ref('wallet_events') }} as events
    where events.token_address = summaries.counterparty_address
  )
