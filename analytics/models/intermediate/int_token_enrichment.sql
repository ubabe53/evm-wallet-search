with registry as (
  select
    1 as chain_id,
    lower(token_address) as token_address,
    symbol,
    name,
    cast(decimals as integer) as decimals,
    recognition_status,
    metadata_source,
    metadata_source_url
  from {{ ref('token_metadata') }}
),

overrides as (
  select
    1 as chain_id,
    lower(token_address) as token_address,
    nullif(trim(symbol), '') as symbol,
    nullif(trim(name), '') as name,
    try_cast(decimals as integer) as decimals,
    nullif(trim(recognition_status), '') as recognition_status,
    nullif(trim(reason), '') as token_label_reason,
    nullif(trim(source_url), '') as source_url
  from {{ ref('token_label_overrides') }}
),

rpc_metadata as (
  select
    1 as chain_id,
    lower(token_address) as token_address,
    nullif(trim(symbol), '') as symbol,
    nullif(trim(name), '') as name,
    try_cast(decimals as integer) as decimals
  {% if var('use_fixture', true) %}
  {% if var('fixture_dataset', 'demo') == 'synthetic' %}
  from {{ ref('token_rpc_metadata_fixture') }}
  {% else %}
  from {{ ref('token_rpc_metadata_demo') }}
  {% endif %}
  {% else %}
  from {{ ref('token_rpc_metadata') }}
  {% endif %}
  where fetch_status in ('complete', 'partial')
),

addresses as (
  select chain_id, token_address from registry
  union
  select chain_id, token_address from overrides
  union
  select chain_id, token_address from rpc_metadata
)

select
  addresses.chain_id,
  addresses.token_address,
  coalesce(overrides.symbol, registry.symbol, rpc_metadata.symbol) as symbol,
  coalesce(overrides.name, registry.name, rpc_metadata.name) as name,
  coalesce(overrides.decimals, registry.decimals, rpc_metadata.decimals) as decimals,
  coalesce(overrides.recognition_status, registry.recognition_status, 'other') as recognition_status,
  case
    when overrides.recognition_status = 'recognized' then 'reviewed_manual_recognized'
    when overrides.recognition_status = 'other' then 'reviewed_manual_other'
    when registry.recognition_status = 'recognized' then 'registry_match'
    else 'no_registry_match'
  end as recognition_reason,
  case
    when overrides.recognition_status is not null then 'manual'
    when registry.recognition_status = 'recognized' then 'registry'
    else 'automatic'
  end as recognition_source,
  'token-recognition-v1' as recognition_version,
  case
    when overrides.token_address is not null then 'manual'
    when registry.token_address is not null then registry.metadata_source
    when rpc_metadata.token_address is not null then 'ethereum_rpc'
  end as metadata_source,
  coalesce(overrides.source_url, registry.metadata_source_url) as metadata_source_url,
  overrides.token_label_reason,
  case
    when coalesce(overrides.symbol, registry.symbol, rpc_metadata.symbol) is not null
      and coalesce(overrides.name, registry.name, rpc_metadata.name) is not null
      and coalesce(overrides.decimals, registry.decimals, rpc_metadata.decimals) is not null
      then 'complete'
    when coalesce(overrides.symbol, registry.symbol, rpc_metadata.symbol) is not null
      or coalesce(overrides.name, registry.name, rpc_metadata.name) is not null
      or coalesce(overrides.decimals, registry.decimals, rpc_metadata.decimals) is not null
      then 'partial'
    else 'unavailable'
  end as metadata_availability
from addresses
left join registry using (chain_id, token_address)
left join overrides using (chain_id, token_address)
left join rpc_metadata using (chain_id, token_address)
