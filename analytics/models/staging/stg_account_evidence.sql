{% if var('use_fixture', true) %}
{% if var('fixture_dataset', 'demo') == 'synthetic' %}
select
  null::integer as chain_id,
  null::varchar as address,
  null::varchar as account_type,
  null::varchar as code_state,
  null::bigint as code_size_bytes,
  null::bigint as observation_block_number,
  null::varchar as observation_block_hash,
  null::timestamptz as observation_block_timestamp,
  null::varchar as finality_policy,
  null::varchar as eip7702_delegation_target,
  null::varchar as fetch_status,
  null::varchar as reason_code,
  null::varchar as evidence_schema_version,
  null::timestamptz as fetched_at
where false
{% else %}
select
  cast(chain_id as integer) as chain_id,
  lower(address) as address,
  account_type,
  code_state,
  cast(code_size_bytes as bigint) as code_size_bytes,
  cast(observation_block_number as bigint) as observation_block_number,
  lower(observation_block_hash) as observation_block_hash,
  cast(observation_block_timestamp as timestamptz) as observation_block_timestamp,
  finality_policy,
  lower(nullif(eip7702_delegation_target, '')) as eip7702_delegation_target,
  fetch_status,
  reason_code,
  evidence_schema_version,
  cast(fetched_at as timestamptz) as fetched_at
from {{ ref('account_evidence_demo') }}
{% endif %}
{% else %}
select
  cast(chain_id as integer) as chain_id,
  lower(address) as address,
  account_type,
  code_state,
  cast(code_size_bytes as bigint) as code_size_bytes,
  cast(observation_block_number as bigint) as observation_block_number,
  lower(observation_block_hash) as observation_block_hash,
  cast(observation_block_timestamp as timestamptz) as observation_block_timestamp,
  finality_policy,
  lower(eip7702_delegation_target) as eip7702_delegation_target,
  fetch_status,
  reason_code,
  evidence_schema_version,
  cast(fetched_at as timestamptz) as fetched_at
from account_evidence.account_evidence
{% endif %}
