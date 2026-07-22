select address
from {{ ref('stg_counterparty_metadata') }}
where chain_id != 1
  or observation_block_number <= 0
  or not regexp_matches(observation_block_hash, '^0x[0-9a-f]{64}$')
  or evidence_schema_version != 'account-evidence-v2'
  or fetch_status not in ('complete', 'failed')
  or (fetch_status = 'failed' and account_type != 'unknown')
  or (fetch_status = 'complete' and account_type = 'unknown')
  or (code_state = 'no_code' and (account_type != 'eoa_candidate' or code_size_bytes != 0))
  or (code_state = 'contract_code' and (account_type != 'contract' or coalesce(code_size_bytes, 0) <= 0))
  or (
    code_state = 'eip7702_delegated'
    and (
      account_type != 'eoa_candidate'
      or code_size_bytes != 23
      or not regexp_matches(eip7702_delegation_target, '^0x[0-9a-f]{40}$')
    )
  )
