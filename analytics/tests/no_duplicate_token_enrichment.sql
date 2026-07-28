select chain_id, token_address
from {{ ref('int_token_enrichment') }}
group by chain_id, token_address
having count(*) > 1
