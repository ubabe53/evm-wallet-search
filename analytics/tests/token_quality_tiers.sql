select
  quality.token_address,
  quality.token_quality,
  quality.token_quality_source_count,
  quality.token_quality_reason,
  reputation.token_reputation,
  reputation.token_reputation_version
from {{ ref('stg_token_metadata') }} as quality
inner join {{ ref('int_token_reputation') }} as reputation using (token_address)
where quality.token_address in (
    '0xebb66a88cedd12bfe3a289df6dfee377f2963f12',
    '0xcf91b70017eabde82c9671e30e5502d312ea6eb2'
  )
  and (
    quality.token_quality != 'listed'
    or quality.token_quality_source_count != 1
    or quality.token_quality_sources != ['coingecko']
    or quality.token_quality_reason != 'single_registry_match'
    or quality.token_quality_version != 'token-quality-v1'
    or reputation.token_reputation != 'unverified'
    or reputation.token_reputation_version != 'token-reputation-v2'
  )

union all

select
  quality.token_address,
  quality.token_quality,
  quality.token_quality_source_count,
  quality.token_quality_reason,
  reputation.token_reputation,
  reputation.token_reputation_version
from {{ ref('stg_token_metadata') }} as quality
inner join {{ ref('int_token_reputation') }} as reputation using (token_address)
where quality.token_address = '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48'
  and (
    quality.token_quality != 'high_confidence'
    or quality.token_quality_reason != 'reviewed_manual_approval'
    or reputation.token_reputation != 'trusted'
    or reputation.token_reputation_version != 'token-reputation-v2'
  )
