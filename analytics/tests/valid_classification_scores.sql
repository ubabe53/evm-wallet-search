select token_address, interaction_legitimacy_score as score, interaction_legitimacy_reasons as reasons
from {{ ref('int_wallet_token_interactions') }}
where interaction_legitimacy_score not between 0 and 100
  or nullif(trim(interaction_legitimacy_reasons), '') is null
