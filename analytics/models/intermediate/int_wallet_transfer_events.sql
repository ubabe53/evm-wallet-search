{% if var('use_fixture', true) %}
  {{ config(materialized='table') }}
{% else %}
  {{ config(materialized='incremental', unique_key=['chain_id', 'wallet_address', 'transaction_hash', 'log_index'], incremental_strategy='merge') }}
{% endif %}

with transfers as (
  select * from {{ ref('stg_transfer_events') }}
),

wallets as (
  select * from {{ ref('stg_wallets') }}
),

tokens as (
  select * from {{ ref('int_token_enrichment') }}
),

counterparties as (
  select * from {{ ref('stg_account_evidence') }}
),

matched as (
  select
    transfers.chain_id,
    transfers.block_number,
    transfers.block_hash,
    transfers.block_timestamp,
    transfers.transaction_hash,
    transfers.transaction_index,
    transfers.transaction_from_address,
    transfers.transaction_to_address,
    transfers.log_index,
    wallets.wallet_address,
    transfers.token_address,
    tokens.symbol as token_symbol,
    tokens.name as token_name,
    tokens.decimals as token_decimals,
    coalesce(tokens.recognition_status, 'other') as recognition_status,
    coalesce(tokens.recognition_reason, 'no_registry_match') as recognition_reason,
    coalesce(tokens.recognition_source, 'automatic') as recognition_source,
    coalesce(tokens.recognition_version, 'token-recognition-v1') as recognition_version,
    tokens.metadata_source,
    tokens.metadata_source_url,
    tokens.token_label_reason,
    coalesce(tokens.metadata_availability, 'unavailable') as metadata_availability,
    transfers.from_address,
    transfers.to_address,
    case
      when transfers.transaction_from_address is null then 'unknown'
      when transfers.transaction_from_address = transfers.from_address then 'transfer_sender'
      when transfers.transaction_from_address = transfers.to_address then 'transfer_recipient'
      else 'other'
    end as transaction_sender_relation,
    case
      when transfers.transaction_to_address is null then 'unknown'
      when transfers.transaction_to_address = transfers.token_address then 'token_contract'
      when transfers.transaction_to_address = transfers.from_address then 'transfer_sender'
      when transfers.transaction_to_address = transfers.to_address then 'transfer_recipient'
      else 'other'
    end as transaction_target_relation,
    case
      when transfers.transaction_from_address is null then null
      else transfers.transaction_from_address != transfers.from_address
    end as is_indirect,
    case
      when transfers.from_address = wallets.wallet_address
        and transfers.to_address = wallets.wallet_address then 'self'
      when transfers.to_address = wallets.wallet_address then 'in'
      when transfers.from_address = wallets.wallet_address then 'out'
    end as direction,
    case
      when transfers.from_address = wallets.wallet_address
        and transfers.to_address = wallets.wallet_address then wallets.wallet_address
      when transfers.from_address = wallets.wallet_address then transfers.to_address
      else transfers.from_address
    end as counterparty_address,
    coalesce(counterparties.account_type, 'unknown') as counterparty_account_type,
    coalesce(counterparties.code_state, 'unknown') as counterparty_code_state,
    counterparties.code_size_bytes as counterparty_code_size_bytes,
    counterparties.observation_block_number as counterparty_observation_block_number,
    counterparties.observation_block_timestamp as counterparty_observation_block_timestamp,
    counterparties.eip7702_delegation_target as counterparty_eip7702_delegation_target,
    coalesce(counterparties.fetch_status, 'not_fetched') as counterparty_evidence_fetch_status,
    coalesce(counterparties.reason_code, 'account_evidence_not_fetched') as counterparty_evidence_reason_code,
    counterparties.evidence_schema_version as counterparty_evidence_schema_version,
    transfers.value_raw
  from transfers
  join wallets
    on transfers.chain_id = wallets.chain_id
    and (
      transfers.from_address = wallets.wallet_address
      or transfers.to_address = wallets.wallet_address
    )
  left join tokens
    on transfers.chain_id = tokens.chain_id
    and transfers.token_address = tokens.token_address
  left join counterparties
    on counterparties.chain_id = transfers.chain_id
    and not (
      transfers.from_address = wallets.wallet_address
      and transfers.to_address = wallets.wallet_address
    )
    and counterparties.address = case
      when transfers.from_address = wallets.wallet_address
        and transfers.to_address = wallets.wallet_address then wallets.wallet_address
      when transfers.from_address = wallets.wallet_address then transfers.to_address
      else transfers.from_address
    end
)

select * from matched
