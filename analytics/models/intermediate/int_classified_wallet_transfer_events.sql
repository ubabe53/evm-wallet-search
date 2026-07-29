select
  events.* exclude (token_status),
  case
    when events.token_status = 'spam' then 'spam'
    when interactions.interaction_legitimacy = 'suspicious' then 'suspected_spam'
    when events.token_quality = 'high_confidence' then 'trusted'
    else 'unverified'
  end as token_status,
  coalesce(interactions.interaction_legitimacy, 'not_suspicious') as interaction_legitimacy,
  coalesce(interactions.interaction_legitimacy_score, 0) as interaction_legitimacy_score,
  coalesce(interactions.interaction_legitimacy_reasons, 'no_interaction_anomaly') as interaction_legitimacy_reasons,
  interactions.interaction_legitimacy_version
from {{ ref('int_wallet_transfer_events') }} as events
left join {{ ref('int_wallet_token_interactions') }} as interactions
  on interactions.chain_id = events.chain_id
  and interactions.wallet_address = events.wallet_address
  and interactions.token_address = events.token_address
