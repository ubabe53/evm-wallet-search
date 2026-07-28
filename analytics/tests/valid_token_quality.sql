select token_address
from {{ ref('int_token_enrichment') }}
where token_quality_source_count != len(token_quality_sources)
  or token_quality_source_count < 0
  or (token_quality = 'high_confidence'
    and not (token_quality_source_count >= 2 or (metadata_source = 'manual' and token_status = 'trusted')))
  or (token_quality = 'listed'
    and (token_quality_source_count != 1 or (metadata_source = 'manual' and token_status = 'trusted')))
  or (token_quality = 'unknown'
    and (token_quality_source_count != 0 or (metadata_source = 'manual' and token_status = 'trusted')))
  or nullif(trim(token_quality_reason), '') is null
  or nullif(trim(token_quality_provenance), '') is null
  or token_quality_version != 'token-quality-v1'
