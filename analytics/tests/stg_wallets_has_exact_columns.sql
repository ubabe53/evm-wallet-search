-- depends_on: {{ ref('stg_wallets') }}

with expected(column_name) as (
  values
    ('chain_id'),
    ('ens'),
    ('wallet_address')
),

actual as (
  select column_name
  from information_schema.columns
  where table_schema = current_schema()
    and table_name = 'stg_wallets'
),

unexpected as (
  select column_name from actual
  except
  select column_name from expected
),

missing as (
  select column_name from expected
  except
  select column_name from actual
)

select 'unexpected' as failure, column_name from unexpected
union all
select 'missing' as failure, column_name from missing
