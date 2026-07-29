select
  chain_id,
  address
from {{ ref('stg_account_evidence') }}
group by chain_id, address
having count(*) > 1
