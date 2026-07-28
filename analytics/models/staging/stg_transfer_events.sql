with raw_transfers as (
  {% if var('use_fixture', true) %}
    select * from {{ ref('raw_transfer_events_fixture') }}
  {% else %}
    -- Force the unconstrained Postgres numeric to text before DuckDB scans it.
    -- depends_on: {{ source('hyperindex', 'transfer_event') }}
    select
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
  {% endif %}
),

normalized as (
  select
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

deduped as (
  select *
  from normalized
  qualify row_number() over (
    partition by chain_id, transaction_hash, log_index
    order by block_number desc
  ) = 1
)

select * from deduped
