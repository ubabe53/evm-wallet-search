with interaction_counts as (
  select
    'interaction:' || wallet_address || ':' || counterparty_address || ':' || token_address || ':' || direction as interaction_id,
    wallet_address,
    counterparty_address,
    token_address,
    coalesce(token_symbol, substr(token_address, 1, 10)) as token_symbol,
    token_status,
    metadata_source,
    metadata_source_url,
    token_reputation,
    token_reputation_score,
    token_reputation_reasons,
    interaction_legitimacy,
    interaction_legitimacy_score,
    interaction_legitimacy_reasons,
    direction,
    count(*) as transfer_count,
    case
      when count(amount_decimal) = count(*) then sum(amount_decimal)
      else null
    end as amount_decimal_sum,
    min(block_timestamp) as first_seen_at,
    max(block_timestamp) as last_seen_at
  from {{ ref('wallet_events') }}
  group by wallet_address, counterparty_address, token_address, token_symbol,
    token_status, metadata_source, metadata_source_url, token_reputation,
    token_reputation_score, token_reputation_reasons, interaction_legitimacy,
    interaction_legitimacy_score, interaction_legitimacy_reasons, direction
),

interactions as (
  select
    *,
    sum(transfer_count) over (
      partition by wallet_address, counterparty_address
    ) as counterparty_transfer_count
  from interaction_counts
),

edge_legs as (
  select
    interaction_id || ':wallet-token' as edge_id,
    interaction_id,
    'wallet_token' as edge_role,
    case when direction = 'out' then 'wallet:' || wallet_address else 'token:' || token_address end as source_node_id,
    case when direction = 'out' then 'token:' || token_address else 'wallet:' || wallet_address end as target_node_id,
    * exclude (interaction_id)
  from interactions

  union all

  select
    interaction_id || ':token-counterparty' as edge_id,
    interaction_id,
    'token_counterparty' as edge_role,
    case when direction = 'out' then 'token:' || token_address else 'counterparty:' || counterparty_address end as source_node_id,
    case when direction = 'out' then 'counterparty:' || counterparty_address else 'token:' || token_address end as target_node_id,
    * exclude (interaction_id)
  from interactions
)

select * from edge_legs
