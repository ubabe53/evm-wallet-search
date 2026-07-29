-- depends_on: {{ ref('timeline_daily') }}

with expected(column_name) as (
  values
    ('chain_id'),
    ('wallet_address'),
    ('block_date'),
    ('token_address'),
    ('token_symbol'),
    ('recognition_status'),
    ('counterparty_account_type'),
    ('direction'),
    ('transfer_count')
),

actual as (
  select column_name
  from information_schema.columns
  where table_schema = current_schema()
    and table_name = 'timeline_daily'
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
