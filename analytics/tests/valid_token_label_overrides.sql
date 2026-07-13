select token_address
from {{ ref('token_label_overrides') }}
where
  not regexp_matches(lower(token_address), '^0x[0-9a-f]{40}$')
  or token_status not in ('trusted', 'unverified', 'suspected_spam', 'spam')
  or (token_status in ('suspected_spam', 'spam') and (nullif(trim(reason), '') is null or nullif(trim(source_url), '') is null))
