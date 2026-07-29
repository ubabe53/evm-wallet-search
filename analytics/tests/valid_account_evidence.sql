select chain_id, address
from {{ ref('stg_account_evidence') }}
where chain_id != 1
  or not regexp_matches(address, '^0x[0-9a-f]{40}$')
  or observation_block_number <= 0
  or not regexp_matches(observation_block_hash, '^0x[0-9a-f]{64}$')
  or observation_block_timestamp is null
  or fetched_at < observation_block_timestamp
  or finality_policy is null
  or not regexp_matches(finality_policy, '^(safe|legacy_latest|latest_minus_[0-9]+)$')
  or evidence_schema_version != 'account-evidence-v2'
  or fetch_status not in ('complete', 'failed')
  or (
    fetch_status = 'failed'
    and (
      account_type != 'unknown'
      or code_state != 'unknown'
      or code_size_bytes is not null
      or eip7702_delegation_target is not null
      or reason_code not in ('code_lookup_missing', 'code_lookup_malformed')
    )
  )
  or (fetch_status = 'complete' and account_type = 'unknown')
  or (
    code_state = 'no_code'
    and (
      account_type != 'eoa_candidate'
      or code_size_bytes != 0
      or eip7702_delegation_target is not null
      or reason_code != 'no_code_observed'
    )
  )
  or (
    code_state = 'contract_code'
    and (
      account_type != 'contract'
      or coalesce(code_size_bytes, 0) <= 0
      or eip7702_delegation_target is not null
      or reason_code != 'contract_code_observed'
    )
  )
  or (
    code_state = 'eip7702_delegated'
    and (
      account_type != 'eoa_candidate'
      or code_size_bytes != 23
      or not coalesce(regexp_matches(eip7702_delegation_target, '^0x[0-9a-f]{40}$'), false)
      or reason_code != 'eip7702_delegation_observed'
    )
  )
  or fetched_at is null
