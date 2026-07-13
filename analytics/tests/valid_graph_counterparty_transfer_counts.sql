with expected as (
  select wallet_address, counterparty_address, count(*) as transfer_count
  from {{ ref('wallet_events') }}
  group by wallet_address, counterparty_address
)

select edges.edge_id
from {{ ref('graph_edges') }} as edges
join expected using (wallet_address, counterparty_address)
where edges.counterparty_transfer_count != expected.transfer_count
