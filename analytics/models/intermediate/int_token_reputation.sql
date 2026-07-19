with token_addresses as (
  select distinct token_address from {{ ref('stg_erc20_transfers') }}
  union
  select token_address from {{ ref('stg_token_metadata') }}
),

tokens as (
  select
    addresses.token_address,
    metadata.symbol,
    metadata.name,
    metadata.token_status as base_token_status,
    metadata.metadata_source,
    metadata.token_label_reason,
    coalesce(metadata.token_quality, 'unknown') as token_quality,
    coalesce(metadata.token_quality_sources, []::varchar[]) as token_quality_sources,
    coalesce(metadata.token_quality_source_count, 0) as token_quality_source_count,
    coalesce(metadata.token_quality_reason, 'no_registry_or_reviewed_approval') as token_quality_reason,
    coalesce(metadata.token_quality_provenance, 'no_recorded_source') as token_quality_provenance,
    coalesce(metadata.token_quality_version, 'token-quality-v1') as token_quality_version,
    lower(coalesce(metadata.name, '') || ' ' || coalesce(metadata.symbol, '')) as metadata_text
  from token_addresses as addresses
  left join {{ ref('stg_token_metadata') }} as metadata using (token_address)
),

trusted_identities as (
  select
    lower(token_address) as token_address,
    lower(symbol) as symbol,
    lower(name) as name,
    metadata_source
  from {{ ref('token_metadata') }}
),

identity_collisions as (
  select
    tokens.token_address,
    count(trusted.token_address) > 0 as has_market_identity_collision,
    count(trusted.token_address) filter (
      where contains(trusted.metadata_source, 'trustwallet')
        or contains(trusted.metadata_source, 'uniswap')
    ) > 0 as has_curated_identity_collision
  from tokens
  left join trusted_identities as trusted
    on trusted.token_address != tokens.token_address
    and (
      (length(trim(coalesce(tokens.symbol, ''))) >= 2 and lower(tokens.symbol) = trusted.symbol)
      or (length(trim(coalesce(tokens.name, ''))) >= 4 and lower(tokens.name) = trusted.name)
    )
  group by tokens.token_address
),

signal_flags as (
  select
    tokens.*,
    regexp_matches(metadata_text, '(https?://|www\.|[a-z0-9-]+\.(com|net|org|io|xyz|finance|app|site))') as has_url,
    regexp_matches(metadata_text, '(^|[^a-z])(claim|visit|reward|voucher|bonus|airdrop|free token|connect wallet)([^a-z]|$)') as has_claim_language,
    coalesce(collisions.has_market_identity_collision, false) as has_market_identity_collision,
    coalesce(collisions.has_curated_identity_collision, false) as has_curated_identity_collision,
    lower(trim(coalesce(symbol, ''))) in ('btc', 'eth')
      or lower(trim(coalesce(name, ''))) in ('bitcoin', 'ethereum') as impersonates_native_asset,
    coalesce((
      select bool_or(
        (length(split_part(lower(wallets.ens), '.', 1)) >= 4 and contains(metadata_text, split_part(lower(wallets.ens), '.', 1)))
        or (length(split_part(lower(wallets.label), ' ', 1)) >= 4 and contains(metadata_text, split_part(lower(wallets.label), ' ', 1)))
      )
      from {{ ref('stg_wallets') }} as wallets
    ), false) as impersonates_configured_wallet
  from tokens
  left join identity_collisions as collisions using (token_address)
),

scored as (
  select
    *,
    least(100,
      case when has_url then 70 else 0 end
      + case when has_claim_language then 30 else 0 end
      + case
          when has_curated_identity_collision then 65
          when has_market_identity_collision then 35
          else 0
        end
      + case when impersonates_native_asset then 65 else 0 end
      + case when impersonates_configured_wallet then 60 else 0 end
    ) as automated_reputation_score,
    concat_ws('; ',
      case when has_url then 'url_in_name_or_symbol' end,
      case when has_claim_language then 'claim_language' end,
      case
        when has_curated_identity_collision then 'curated_token_identity_collision'
        when has_market_identity_collision then 'coingecko_token_identity_collision'
      end,
      case when impersonates_native_asset then 'native_asset_impersonation' end,
      case when impersonates_configured_wallet then 'configured_wallet_impersonation' end
    ) as automated_reputation_reasons
  from signal_flags
)

select
  token_address,
  case
    when metadata_source = 'manual' and base_token_status = 'spam' then 'spam'
    when automated_reputation_score >= 60 then 'suspected_spam'
    when token_quality = 'high_confidence' then 'trusted'
    else 'unverified'
  end as token_reputation,
  case
    when metadata_source = 'manual' and base_token_status = 'spam' then 100
    else automated_reputation_score
  end as token_reputation_score,
  case
    when metadata_source = 'manual' and base_token_status = 'spam'
      then coalesce(token_label_reason, 'reviewed_spam')
    when automated_reputation_reasons != '' then automated_reputation_reasons
    when token_quality = 'high_confidence' then token_quality_reason
    else 'no_reputation_signal'
  end as token_reputation_reasons,
  'token-reputation-v2' as token_reputation_version,
  token_quality,
  token_quality_sources,
  token_quality_source_count,
  token_quality_reason,
  token_quality_provenance,
  token_quality_version
from scored
