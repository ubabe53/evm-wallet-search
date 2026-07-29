-- depends_on: {{ ref('counterparty_summary') }}
-- depends_on: {{ ref('int_token_enrichment') }}
-- depends_on: {{ ref('int_wallet_transfer_events') }}
-- depends_on: {{ ref('pipeline_metadata') }}
-- depends_on: {{ ref('raw_transfer_events_fixture') }}
-- depends_on: {{ ref('stg_account_evidence') }}
-- depends_on: {{ ref('stg_transfer_events') }}
-- depends_on: {{ ref('stg_wallets') }}
-- depends_on: {{ ref('timeline_daily') }}
-- depends_on: {{ ref('token_label_overrides') }}
-- depends_on: {{ ref('token_metadata') }}
-- depends_on: {{ ref('token_rpc_metadata') }}
-- depends_on: {{ ref('token_rpc_metadata_fixture') }}
-- depends_on: {{ ref('token_summary') }}
-- depends_on: {{ ref('wallet_events') }}
-- depends_on: {{ ref('wallets') }}

with expected(table_name, table_type) as (
  values
    ('counterparty_summary', 'BASE TABLE'),
    ('int_token_enrichment', 'VIEW'),
    ('int_wallet_transfer_events', 'BASE TABLE'),
    ('pipeline_metadata', 'BASE TABLE'),
    ('raw_transfer_events_fixture', 'BASE TABLE'),
    ('stg_account_evidence', 'VIEW'),
    ('stg_transfer_events', 'VIEW'),
    ('stg_wallets', 'VIEW'),
    ('timeline_daily', 'BASE TABLE'),
    ('token_label_overrides', 'BASE TABLE'),
    ('token_metadata', 'BASE TABLE'),
    ('token_rpc_metadata', 'BASE TABLE'),
    ('token_rpc_metadata_fixture', 'BASE TABLE'),
    ('token_summary', 'BASE TABLE'),
    ('wallet_events', 'BASE TABLE'),
    ('wallets', 'BASE TABLE')
),

actual as (
  select table_name, table_type
  from information_schema.tables
  where table_catalog = current_database()
    and table_schema = current_schema()
),

unexpected as (
  select table_name, table_type from actual
  except
  select table_name, table_type from expected
),

missing as (
  select table_name, table_type from expected
  except
  select table_name, table_type from actual
)

select 'unexpected' as failure, table_name, table_type from unexpected
union all
select 'missing' as failure, table_name, table_type from missing
