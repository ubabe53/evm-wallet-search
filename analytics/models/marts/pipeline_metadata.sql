with event_metrics as (
  select
    wallet_id,
    count(*) as transfer_count,
    count(distinct token_address) as token_count,
    count(distinct counterparty_address) as counterparty_count,
    count(*) filter (where token_status in ('trusted', 'unverified')) as non_spam_transfer_count,
    count(distinct token_address) filter (where token_status in ('trusted', 'unverified')) as non_spam_token_count,
    count(distinct counterparty_address) filter (where token_status in ('trusted', 'unverified')) as non_spam_counterparty_count,
    count(*) filter (where token_status in ('suspected_spam', 'spam')) as spam_transfer_count,
    count(distinct token_address) filter (where token_status in ('suspected_spam', 'spam')) as spam_token_count,
    count(*) filter (where token_status = 'suspected_spam') as suspected_spam_transfer_count,
    count(distinct token_address) filter (where token_status = 'suspected_spam') as suspected_spam_token_count,
    min(block_timestamp) as first_event_at,
    max(block_timestamp) as last_event_at
  from {{ ref('wallet_events') }}
  group by wallet_id
),

interaction_metrics as (
  select wallet_id, count(*) as interaction_count
  from (
    select distinct wallet_id, counterparty_address, token_address, direction
    from {{ ref('wallet_events') }}
  )
  group by wallet_id
),

timeline_metrics as (
  select wallet_id, count(*) as timeline_row_count
  from {{ ref('timeline_daily') }}
  group by wallet_id
)

select
  wallets.wallet_id,
  wallets.ens,
  wallets.wallet_address,
  1 as chain_id,
  {% if var('use_fixture', true) %}'fixture'{% else %}'hyperindex'{% endif %} as data_source,
  current_timestamp as generated_at,
  coalesce(events.transfer_count, 0) as transfer_count,
  coalesce(events.token_count, 0) as token_count,
  coalesce(events.counterparty_count, 0) as counterparty_count,
  coalesce(events.non_spam_transfer_count, 0) as non_spam_transfer_count,
  coalesce(events.non_spam_token_count, 0) as non_spam_token_count,
  coalesce(events.non_spam_counterparty_count, 0) as non_spam_counterparty_count,
  coalesce(events.spam_transfer_count, 0) as spam_transfer_count,
  coalesce(events.spam_token_count, 0) as spam_token_count,
  coalesce(events.suspected_spam_transfer_count, 0) as suspected_spam_transfer_count,
  coalesce(events.suspected_spam_token_count, 0) as suspected_spam_token_count,
  coalesce(interactions.interaction_count, 0) as interaction_count,
  coalesce(timeline.timeline_row_count, 0) as timeline_row_count,
  events.first_event_at,
  events.last_event_at
from {{ ref('stg_wallets') }} as wallets
left join event_metrics as events using (wallet_id)
left join interaction_metrics as interactions using (wallet_id)
left join timeline_metrics as timeline using (wallet_id)
