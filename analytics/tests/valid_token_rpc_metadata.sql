with metadata as (
  select * from {{ ref('token_rpc_metadata') }}
  union all
  select * from {{ ref('token_rpc_metadata_fixture') }}
  union all
  select * from {{ ref('token_rpc_metadata_demo') }}
),

invalid_rows as (
  select token_address
  from metadata
  where
    not regexp_matches(lower(token_address), '^0x[0-9a-f]{40}$')
    or fetch_status not in ('complete', 'partial', 'failed')
    or rpc_block_number <= 0
    or decimals < 0
    or decimals > 255
    or (fetch_status = 'complete' and (nullif(name, '') is null or nullif(symbol, '') is null or decimals is null))
),

duplicate_rows as (
  select token_address
  from metadata
  group by token_address
  having count(*) > 1
)

select * from invalid_rows
union all
select * from duplicate_rows
