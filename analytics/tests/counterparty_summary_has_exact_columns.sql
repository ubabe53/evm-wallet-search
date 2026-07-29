-- depends_on: {{ ref('counterparty_summary') }}

with expected(column_name) as (
  values
    ('chain_id'),
    ('wallet_address'),
    ('counterparty_address'),
    ('account_type'),
    ('code_state'),
    ('observation_block_number'),
    ('eip7702_delegation_target'),
    ('recognition_status'),
    ('transfer_count'),
    ('inbound_transfer_count'),
    ('outbound_transfer_count'),
    ('token_count'),
    ('first_seen_at'),
    ('last_seen_at')
),

actual as (
  select column_name
  from information_schema.columns
  where table_schema = current_schema()
    and table_name = 'counterparty_summary'
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
