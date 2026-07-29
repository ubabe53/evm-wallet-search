-- depends_on: {{ ref('int_wallet_transfer_events') }}

with expected(column_name) as (
  values
    ('chain_id'),
    ('block_number'),
    ('block_hash'),
    ('block_timestamp'),
    ('transaction_hash'),
    ('transaction_index'),
    ('transaction_from_address'),
    ('transaction_to_address'),
    ('log_index'),
    ('wallet_address'),
    ('token_address'),
    ('token_symbol'),
    ('token_name'),
    ('token_decimals'),
    ('recognition_status'),
    ('recognition_reason'),
    ('recognition_source'),
    ('recognition_version'),
    ('metadata_source'),
    ('metadata_source_url'),
    ('token_label_reason'),
    ('metadata_availability'),
    ('from_address'),
    ('to_address'),
    ('transaction_sender_relation'),
    ('transaction_target_relation'),
    ('is_indirect'),
    ('direction'),
    ('counterparty_address'),
    ('counterparty_account_type'),
    ('counterparty_code_state'),
    ('counterparty_code_size_bytes'),
    ('counterparty_observation_block_number'),
    ('counterparty_observation_block_timestamp'),
    ('counterparty_eip7702_delegation_target'),
    ('counterparty_evidence_fetch_status'),
    ('counterparty_evidence_reason_code'),
    ('counterparty_evidence_schema_version'),
    ('value_raw')
),

actual as (
  select column_name
  from information_schema.columns
  where table_schema = current_schema()
    and table_name = 'int_wallet_transfer_events'
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
