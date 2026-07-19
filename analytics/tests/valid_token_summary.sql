with expected as (
  select
    wallet_address,
    token_address,
    token_status,
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
    ) as recipient_account_count
  from {{ ref('wallet_events') }}
  group by wallet_address, token_address, token_status
)
select summaries.*
from {{ ref('token_summary') }} as summaries
inner join expected using (wallet_address, token_address, token_status)
where summaries.transfer_count != summaries.inbound_transfer_count + summaries.outbound_transfer_count
  or summaries.indirect_inbound_transfer_count > summaries.inbound_transfer_count
  or summaries.indirect_outbound_transfer_count > summaries.outbound_transfer_count
  or summaries.counterparty_count != expected.counterparty_count
  or summaries.sender_account_count != expected.sender_account_count
  or summaries.recipient_account_count != expected.recipient_account_count
