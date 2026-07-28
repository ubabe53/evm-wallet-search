with registry as (
  select
    1 as chain_id,
    lower(token_address) as token_address,
    symbol,
    name,
    cast(decimals as integer) as decimals,
    token_status,
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
    nullif(trim(token_status), '') as token_status,
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
    try_cast(decimals as integer) as decimals,
    cast(rpc_block_number as bigint) as rpc_block_number
  {% if var('use_fixture', true) %}
  from {{ ref('token_rpc_metadata_fixture') }}
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
),

resolved as (
  select
    addresses.chain_id,
    addresses.token_address,
    coalesce(overrides.symbol, registry.symbol, rpc_metadata.symbol) as symbol,
    coalesce(overrides.name, registry.name, rpc_metadata.name) as name,
    coalesce(overrides.decimals, registry.decimals, rpc_metadata.decimals) as decimals,
    coalesce(overrides.token_status, 'unverified') as token_status,
    case
      when overrides.token_status = 'spam' then 'other'
      when overrides.token_status = 'trusted' then 'recognized'
      when registry.recognition_status = 'recognized' then 'recognized'
      else 'other'
    end as recognition_status,
    case
      when overrides.token_status = 'spam' then 'reviewed_manual_other'
      when overrides.token_status = 'trusted' then 'reviewed_manual_recognized'
      when registry.recognition_status = 'recognized' then 'registry_match'
      else 'no_registry_match'
    end as recognition_reason,
    case
      when overrides.token_status in ('spam', 'trusted') then 'manual'
      when registry.recognition_status = 'recognized' then 'registry'
      else 'automatic'
    end as recognition_source,
    case
      when overrides.token_address is not null then 'manual'
      when registry.token_address is not null then registry.metadata_source
      when rpc_metadata.token_address is not null then 'ethereum_rpc'
    end as metadata_source,
    coalesce(overrides.source_url, registry.metadata_source_url) as metadata_source_url,
    overrides.token_label_reason,
    case
      when registry.token_address is null then []::varchar[]
      else string_split(registry.metadata_source, '+')
    end as token_quality_sources,
    case
      when registry.token_address is null then 0
      else 1 + length(registry.metadata_source) - length(replace(registry.metadata_source, '+', ''))
    end as token_quality_source_count,
    case
      when overrides.token_status = 'trusted' then 'high_confidence'
      when registry.token_address is not null
        and 1 + length(registry.metadata_source) - length(replace(registry.metadata_source, '+', '')) >= 2
        then 'high_confidence'
      when registry.token_address is not null then 'listed'
      else 'unknown'
    end as token_quality,
    case
      when overrides.token_status = 'trusted' then 'reviewed_manual_approval'
      when registry.token_address is not null
        and 1 + length(registry.metadata_source) - length(replace(registry.metadata_source, '+', '')) >= 2
        then 'multiple_independent_registry_matches'
      when registry.token_address is not null then 'single_registry_match'
      when rpc_metadata.token_address is not null then 'rpc_metadata_only'
      else 'no_registry_or_reviewed_approval'
    end as token_quality_reason,
    case
      when overrides.token_status = 'trusted' then coalesce(overrides.source_url, 'manual_override')
      when registry.token_address is not null then registry.metadata_source_url
      when rpc_metadata.token_address is not null and rpc_metadata.rpc_block_number is not null
        then 'ethereum_rpc_block:' || cast(rpc_metadata.rpc_block_number as varchar)
      when rpc_metadata.token_address is not null then 'ethereum_rpc'
      else 'no_recorded_source'
    end as token_quality_provenance
  from addresses
  left join registry using (chain_id, token_address)
  left join overrides using (chain_id, token_address)
  left join rpc_metadata using (chain_id, token_address)
)

select
  *,
  case
    when symbol is not null and name is not null and decimals is not null then 'complete'
    when symbol is not null or name is not null or decimals is not null then 'partial'
    else 'unavailable'
  end as metadata_availability,
  'token-quality-v1' as token_quality_version,
  'token-recognition-v1' as recognition_version
from resolved
