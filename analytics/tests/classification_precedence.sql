select transfer_id
from {{ ref('wallet_events') }}
where (token_reputation = 'spam' and token_status != 'spam')
  or (
    (token_reputation = 'suspected_spam' or interaction_legitimacy = 'suspicious')
    and token_reputation != 'spam'
    and token_status != 'suspected_spam'
  )
  or (
    token_reputation = 'trusted'
    and interaction_legitimacy != 'suspicious'
    and token_status != 'trusted'
  )
