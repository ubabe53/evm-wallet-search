with raw_transfers as (
  {% if var('use_fixture', true) %}
    select 'fixture' as source_name, * from {{ ref('raw_transfer_events_fixture') }}
  {% else %}
    -- Force the unconstrained Postgres numeric to text before DuckDB scans it.
    -- depends_on: {{ source('hyperindex', 'transfer_event') }}
    select
      'hyperindex_public' as source_name,
      chain_id,
      block_number,
      block_hash,
      block_timestamp,
      transaction_hash,
      transaction_index,
      transaction_from_address,
      transaction_to_address,
      log_index,
      token_address,
      from_address,
      to_address,
      value_raw
    from postgres_query(
      'hyperindex',
      'select chain_id, block_number, block_hash, block_timestamp, transaction_hash, transaction_index, transaction_from_address, transaction_to_address, log_index, token_address, from_address, to_address, value_raw::text as value_raw from public."Erc20Transfer" where block_number between {{ env_var("EVM_WALLET_SNAPSHOT_START_BLOCK") }} and {{ env_var("EVM_WALLET_SNAPSHOT_END_BLOCK") }}'
    )
    {% if env_var('EVM_WALLET_SHARED_RAW_ENABLED', 'false') == 'true' %}
    union all
    -- depends_on: {{ source('bounded_wallet_scan', 'transfer_event') }}
    select
      'bounded_scan' as source_name,
      chain_id,
      block_number,
      block_hash,
      block_timestamp,
      transaction_hash,
      transaction_index,
      transaction_from_address,
      transaction_to_address,
      log_index,
      token_address,
      from_address,
      to_address,
      value_raw
    from postgres_query(
      'hyperindex',
      'select chain_id, block_number, block_hash, block_timestamp, transaction_hash, transaction_index, transaction_from_address, transaction_to_address, log_index, token_address, from_address, to_address, value_raw::text as value_raw from wallet_scan.transfer_events where block_number between {{ env_var("EVM_WALLET_SNAPSHOT_START_BLOCK") }} and {{ env_var("EVM_WALLET_SNAPSHOT_END_BLOCK") }}'
    )
    {% endif %}
  {% endif %}
),

normalized as (
  select
    source_name,
    cast(chain_id as integer) as chain_id,
    cast(block_number as bigint) as block_number,
    lower(cast(block_hash as varchar)) as block_hash,
    to_timestamp(cast(block_timestamp as bigint)) as block_timestamp,
    lower(cast(transaction_hash as varchar)) as transaction_hash,
    cast(transaction_index as integer) as transaction_index,
    lower(nullif(cast(transaction_from_address as varchar), '')) as transaction_from_address,
    lower(nullif(cast(transaction_to_address as varchar), '')) as transaction_to_address,
    cast(log_index as integer) as log_index,
    lower(cast(token_address as varchar)) as token_address,
    lower(cast(from_address as varchar)) as from_address,
    lower(cast(to_address as varchar)) as to_address,
    value_raw
  from raw_transfers
),

source_conflicts as (
  select chain_id, transaction_hash, log_index
  from normalized
  group by chain_id, transaction_hash, log_index
  having count(distinct struct_pack(
    block_number := block_number,
    block_hash := block_hash,
    block_timestamp := block_timestamp,
    transaction_index := transaction_index,
    transaction_from_address := transaction_from_address,
    transaction_to_address := transaction_to_address,
    token_address := token_address,
    from_address := from_address,
    to_address := to_address,
    value_raw := value_raw
  )) > 1
),

conflict_guard as (
  select case
    when exists (select 1 from source_conflicts)
      then error('Raw transfer sources conflict on canonical event identity')
    else true
  end as sources_agree
),

deduped as (
  select *
  from normalized
  qualify row_number() over (
    partition by chain_id, transaction_hash, log_index
    order by
      case source_name
        when 'hyperindex_public' then 1
        when 'bounded_scan' then 2
        else 3
      end
  ) = 1
)

select deduped.* exclude (source_name)
from deduped
cross join conflict_guard
where conflict_guard.sources_agree
