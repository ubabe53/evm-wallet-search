-- depends_on: {{ ref('token_summary') }}

with expected(column_name) as (
  values
    ('chain_id'),
    ('wallet_address'),
    ('token_address'),
    ('token_symbol'),
    ('token_name'),
    ('recognition_status'),
    ('counterparty_account_type'),
    ('transfer_count'),
    ('inbound_transfer_count'),
    ('outbound_transfer_count'),
    ('self_transfer_count'),
    ('indirect_inbound_transfer_count'),
    ('indirect_outbound_transfer_count'),
    ('counterparty_count'),
    ('sender_account_count'),
    ('recipient_account_count')
),

actual as (
  select column_name
  from information_schema.columns
  where table_schema = current_schema()
    and table_name = 'token_summary'
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
