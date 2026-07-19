with metrics as (
  select
    wallet_id,
    wallet_address,
    token_address,
    count(*) as transfer_count,
    count(distinct counterparty_address) as distinct_counterparty_count,
    count(*) filter (where direction = 'in') as inbound_transfer_count,
    count(*) filter (where direction = 'out') as outbound_transfer_count,
    count(*) filter (where direction = 'in' and is_indirect) as indirect_inbound_transfer_count,
    count(*) filter (where direction = 'out' and is_indirect) as indirect_outbound_transfer_count,
    count(*) filter (
      where direction = 'out' and transaction_sender_relation != 'unknown'
    ) as evidenced_outbound_transfer_count,
    count(*) filter (
      where direction = 'out' and transaction_sender_relation = 'transfer_sender'
    ) as sender_matched_outbound_transfer_count,
    min(block_timestamp) as first_seen_at,
    max(block_timestamp) as last_seen_at,
    date_diff('minute', min(block_timestamp), max(block_timestamp)) as active_minutes
  from {{ ref('int_wallet_transfer_events') }}
  group by wallet_id, wallet_address, token_address
),

signal_flags as (
  select
    *,
    distinct_counterparty_count >= 100
      and transfer_count <= distinct_counterparty_count * 1.25 as is_broad_spray,
    greatest(inbound_transfer_count, outbound_transfer_count) / transfer_count >= 0.98 as is_one_way,
    outbound_transfer_count / transfer_count >= 0.98 as appears_wallet_outbound,
    outbound_transfer_count > 0
      and evidenced_outbound_transfer_count = outbound_transfer_count
      and sender_matched_outbound_transfer_count = outbound_transfer_count
      as has_complete_wallet_sender_evidence
  from metrics
),

scored as (
  select
    *,
    least(100,
      case when is_broad_spray then 45 else 0 end
      + case when is_broad_spray and active_minutes <= 4320 then 20 else 0 end
      + case when is_broad_spray and is_one_way then 15 else 0 end
      + case
          when is_broad_spray and appears_wallet_outbound and has_complete_wallet_sender_evidence
            then 20
          else 0
        end
    ) as interaction_legitimacy_score,
    concat_ws('; ',
      case when is_broad_spray then 'broad_one_transfer_per_counterparty_spray' end,
      case when is_broad_spray and active_minutes <= 4320 then 'short_distribution_window' end,
      case when is_broad_spray and is_one_way then 'almost_entirely_one_direction' end,
      case
        when is_broad_spray and appears_wallet_outbound and has_complete_wallet_sender_evidence
          then 'mass_outbound_transaction_sender_matches_wallet'
      end
    ) as interaction_legitimacy_reasons
  from signal_flags
)

select
  * exclude (
    is_broad_spray,
    is_one_way,
    appears_wallet_outbound,
    has_complete_wallet_sender_evidence,
    interaction_legitimacy_reasons
  ),
  case
    when interaction_legitimacy_score >= 60 then 'suspicious'
    when interaction_legitimacy_score >= 20 then 'uncertain'
    else 'not_suspicious'
  end as interaction_legitimacy,
  case
    when interaction_legitimacy_reasons = '' then 'no_interaction_anomaly'
    else interaction_legitimacy_reasons
  end as interaction_legitimacy_reasons,
  'interaction-legitimacy-v2' as interaction_legitimacy_version
from scored
