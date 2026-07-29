-- depends_on: {{ ref('wallet_events') }}

with expected(column_name) as (
  values
    ('chain_id'),
    ('wallet_address'),
    ('block_number'),
    ('block_timestamp'),
    ('transaction_hash'),
    ('transaction_index'),
    ('log_index'),
    ('token_address'),
    ('token_symbol'),
    ('token_name'),
    ('recognition_status'),
    ('direction'),
    ('is_indirect'),
    ('counterparty_address'),
    ('counterparty_account_type'),
    ('counterparty_code_state'),
    ('counterparty_observation_block_number'),
    ('counterparty_eip7702_delegation_target')
),

actual as (
  select column_name
  from information_schema.columns
  where table_schema = '{{ target.schema }}'
    and table_name = 'wallet_events'
)

select 'missing' as issue, expected.column_name
from expected
left join actual using (column_name)
where actual.column_name is null

union all

select 'unexpected' as issue, actual.column_name
from actual
left join expected using (column_name)
where expected.column_name is null
