with self_event as (
  select *
  from {{ ref('wallet_events') }}
  where transfer_id = '1-0xself-0'
),

self_token_summary as (
  select *
  from {{ ref('token_summary') }}
  where token_address = '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48'
)

select 'event_direction' as failure
where not exists (
  select 1
  from self_event
  where direction = 'self'
    and from_address = wallet_address
    and to_address = wallet_address
    and counterparty_address = wallet_address
    and counterparty_account_type = 'unknown'
    and counterparty_evidence_fetch_status = 'not_fetched'
)

union all

select 'token_summary_reconciliation' as failure
where not exists (
  select 1
  from self_token_summary
  where self_transfer_count = 1
    and transfer_count = inbound_transfer_count + outbound_transfer_count + self_transfer_count
)

union all

select 'graph_edge' as failure
where exists (
  select 1
  from {{ ref('graph_edges') }}
  where counterparty_address = wallet_address
)

union all

select 'graph_node' as failure
where exists (
  select 1
  from {{ ref('graph_nodes') }}
  where node_id = 'counterparty:0xd8da6bf26964af9d7eed9e03e53415d37aa96045'
)

union all

select 'timeline_direction' as failure
where not exists (
  select 1
  from {{ ref('timeline_daily') }}
  where direction = 'self'
    and token_address = '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48'
    and transfer_count = 1
)
