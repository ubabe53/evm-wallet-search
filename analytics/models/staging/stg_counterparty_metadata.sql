{% if var('use_fixture', true) %}
select
  null::integer as chain_id,
  null::varchar as address,
  null::varchar as account_type,
  null::varchar as code_state,
  null::bigint as code_size_bytes,
  null::bigint as observation_block_number,
  null::varchar as observation_block_hash,
  null::varchar as observation_block_timestamp,
  null::varchar as eip7702_delegation_target,
  null::varchar as fetch_status,
  null::varchar as reason_codes,
  null::varchar as evidence_schema_version,
  null::varchar as fetched_at
where false
{% else %}
select
  cast(chain_id as integer) as chain_id,
  lower(address) as address,
  account_type,
  code_state,
  code_size_bytes,
  observation_block_number,
  lower(observation_block_hash) as observation_block_hash,
  cast(observation_block_timestamp as varchar) as observation_block_timestamp,
  eip7702_delegation_target,
  fetch_status,
  reason_code as reason_codes,
  evidence_schema_version,
  cast(fetched_at as varchar) as fetched_at
from account_evidence.account_evidence
{% endif %}
