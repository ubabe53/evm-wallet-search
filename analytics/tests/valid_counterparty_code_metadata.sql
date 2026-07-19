select address
from {{ ref('stg_counterparty_metadata') }}
where chain_id != 1
  or observation_block_number <= 0
  or coverage_end_block != observation_block_number
  or evidence_schema_version != 'account-evidence-v1'
  or (fetch_status = 'failed' and account_type != 'unknown')
  or (fetch_status = 'failed' and erc4337_effective_coverage is not null)
  or (
    code_state = 'unknown'
    and coalesce(erc4337_observed, false)
    and fetch_status != 'partial'
  )
  or (
    fetch_status = 'complete'
    and (
      safe_verification_status = 'not_checked'
      or contains(reason_codes, 'erc4337_not_checked')
      or erc4337_effective_coverage is null
      or erc4337_failed_ranges is not null
      or coalesce(erc4337_block_chunk_size, 0) <= 0
      or coalesce(erc4337_address_batch_size, 0) <= 0
    )
  )
  or (erc4337_failed_ranges is not null and fetch_status = 'complete')
  or (code_state = 'no_code' and (account_type != 'eoa_candidate' or code_size_bytes != 0))
  or (code_state = 'contract_code' and coalesce(code_size_bytes, 0) <= 0)
  or (
    code_state = 'eip7702_delegated'
    and (
      account_type != 'eip7702_delegated'
      or observation_block_number < 22431084
      or code_size_bytes != 23
      or not regexp_matches(eip7702_delegation_target, '^0x[0-9a-f]{40}$')
    )
  )
  or (account_type = 'safe' and not coalesce(safe_verified, false))
  or (
    coalesce(safe_verified, false)
    and (
      account_type not in ('safe', 'eip7702_delegated')
      or safe_verification_status != 'verified'
      or safe_version is null
      or safe_singleton_address is null
      or safe_owner_count <= 0
      or safe_threshold <= 0
      or safe_threshold > safe_owner_count
    )
  )
  or (account_type = 'erc4337_account' and not coalesce(erc4337_observed, false))
  or (
    coalesce(erc4337_observed, false)
    and (
      account_type not in ('erc4337_account', 'safe', 'eip7702_delegated')
      or coalesce(erc4337_user_operation_count, 0) <= 0
      or erc4337_first_observed_block is null
      or erc4337_last_observed_block < erc4337_first_observed_block
      or erc4337_entrypoint_address is null
      or erc4337_entrypoint_version is null
      or erc4337_entrypoint_source is null
      or erc4337_entrypoint_deployment_block is null
      or erc4337_effective_coverage is null
    )
  )
