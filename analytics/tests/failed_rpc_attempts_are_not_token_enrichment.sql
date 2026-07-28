with rpc_attempts as (
  select lower(token_address) as token_address, fetch_status
  {% if var('use_fixture', true) %}
  from {{ ref('token_rpc_metadata_fixture') }}
  {% else %}
  from {{ ref('token_rpc_metadata') }}
  {% endif %}
)

select enrichment.chain_id, enrichment.token_address
from {{ ref('int_token_enrichment') }} as enrichment
inner join rpc_attempts
  on rpc_attempts.token_address = enrichment.token_address
  and rpc_attempts.fetch_status = 'failed'
left join {{ ref('token_metadata') }} as registry
  on lower(registry.token_address) = enrichment.token_address
left join {{ ref('token_label_overrides') }} as overrides
  on lower(overrides.token_address) = enrichment.token_address
where enrichment.chain_id = 1
  and registry.token_address is null
  and overrides.token_address is null
