select
  cast(chain_id as integer) as chain_id,
  lower(address) as address,
  account_type,
  code_state,
  try_cast(code_size_bytes as bigint) as code_size_bytes,
  cast(observation_block_number as bigint) as observation_block_number,
  cast(observation_block_timestamp as varchar) as observation_block_timestamp,
  nullif(lower(trim(eip7702_delegation_target)), '') as eip7702_delegation_target,
  try_cast(safe_verified as boolean) as safe_verified,
  safe_verification_status,
  nullif(trim(safe_version), '') as safe_version,
  nullif(lower(trim(safe_singleton_address)), '') as safe_singleton_address,
  try_cast(safe_owner_count as integer) as safe_owner_count,
  try_cast(safe_threshold as integer) as safe_threshold,
  try_cast(erc4337_observed as boolean) as erc4337_observed,
  try_cast(erc4337_user_operation_count as bigint) as erc4337_user_operation_count,
  try_cast(erc4337_first_observed_block as bigint) as erc4337_first_observed_block,
  try_cast(erc4337_last_observed_block as bigint) as erc4337_last_observed_block,
  nullif(lower(trim(erc4337_entrypoint_address)), '') as erc4337_entrypoint_address,
  nullif(trim(erc4337_entrypoint_version), '') as erc4337_entrypoint_version,
  nullif(trim(erc4337_entrypoint_source), '') as erc4337_entrypoint_source,
  fetch_status,
  reason_codes,
  coverage_scope,
  try_cast(coverage_start_block as bigint) as coverage_start_block,
  cast(coverage_end_block as bigint) as coverage_end_block,
  evidence_schema_version,
  cast(fetched_at as varchar) as fetched_at
{% if var('use_fixture', true) %}
from {{ ref('counterparty_code_metadata_fixture') }}
{% else %}
from {{ ref('counterparty_code_metadata') }}
{% endif %}
