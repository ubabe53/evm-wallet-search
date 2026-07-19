select
  events.* exclude (token_status),
  case
    when reputation.token_reputation = 'spam' then 'spam'
    when reputation.token_reputation = 'suspected_spam'
      or interactions.interaction_legitimacy = 'suspicious' then 'suspected_spam'
    when events.token_quality = 'high_confidence' then 'trusted'
    else 'unverified'
  end as token_status,
  coalesce(reputation.token_reputation, 'unverified') as token_reputation,
  coalesce(reputation.token_reputation_score, 0) as token_reputation_score,
  coalesce(reputation.token_reputation_reasons, 'no_reputation_signal') as token_reputation_reasons,
  reputation.token_reputation_version,
  coalesce(interactions.interaction_legitimacy, 'not_suspicious') as interaction_legitimacy,
  coalesce(interactions.interaction_legitimacy_score, 0) as interaction_legitimacy_score,
  coalesce(interactions.interaction_legitimacy_reasons, 'no_interaction_anomaly') as interaction_legitimacy_reasons,
  interactions.interaction_legitimacy_version
from {{ ref('int_wallet_transfer_events') }} as events
left join {{ ref('int_token_reputation') }} as reputation using (token_address)
left join {{ ref('int_wallet_token_interactions') }} as interactions
  on interactions.wallet_id = events.wallet_id
  and interactions.token_address = events.token_address
