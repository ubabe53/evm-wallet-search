with transfers as (
  select * from {{ ref('stg_erc20_transfers') }}
),

wallets as (
  select * from {{ ref('stg_wallets') }}
),

tokens as (
  select * from {{ ref('stg_token_metadata') }}
),

counterparties as (
  select * from {{ ref('stg_counterparty_metadata') }}
),

matched as (
  select
    transfers.transfer_id,
    transfers.chain_id,
    transfers.block_number,
    transfers.block_timestamp,
    cast(transfers.block_timestamp as date) as block_date,
    transfers.transaction_hash,
    transfers.transaction_index,
    transfers.transaction_from_address,
    transfers.transaction_to_address,
    transfers.log_index,
    wallets.wallet_id,
    wallets.ens,
    wallets.wallet_address,
    transfers.token_address,
    tokens.symbol as token_symbol,
    tokens.name as token_name,
    tokens.decimals as token_decimals,
    coalesce(tokens.token_status, 'unverified') as token_status,
    tokens.metadata_source,
    tokens.metadata_source_url,
    tokens.token_label_reason,
    coalesce(tokens.metadata_availability, 'unavailable') as metadata_availability,
    coalesce(tokens.token_quality, 'unknown') as token_quality,
    coalesce(tokens.token_quality_sources, []::varchar[]) as token_quality_sources,
    coalesce(tokens.token_quality_source_count, 0) as token_quality_source_count,
    coalesce(tokens.token_quality_reason, 'no_registry_or_reviewed_approval') as token_quality_reason,
    coalesce(tokens.token_quality_provenance, 'no_recorded_source') as token_quality_provenance,
    coalesce(tokens.token_quality_version, 'token-quality-v1') as token_quality_version,
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
      when transfers.from_address = wallets.wallet_address then 'out'
      when transfers.to_address = wallets.wallet_address then 'in'
    end as direction,
    case
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
    coalesce(counterparties.reason_codes, 'account_evidence_not_fetched') as counterparty_evidence_reason_codes,
    counterparties.coverage_scope as counterparty_evidence_coverage_scope,
    counterparties.coverage_start_block as counterparty_evidence_coverage_start_block,
    counterparties.coverage_end_block as counterparty_evidence_coverage_end_block,
    counterparties.evidence_schema_version as counterparty_evidence_schema_version,
    transfers.value_raw,
    case
      when tokens.decimals is not null
        then try_cast(transfers.value_raw as double) / pow(10, tokens.decimals)
      else null
    end as amount_decimal
  from transfers
  join wallets
    on transfers.from_address = wallets.wallet_address
    or transfers.to_address = wallets.wallet_address
  left join tokens
    on transfers.token_address = tokens.token_address
  left join counterparties
    on counterparties.chain_id = transfers.chain_id
    and counterparties.address = case
      when transfers.from_address = wallets.wallet_address then transfers.to_address
      else transfers.from_address
    end
)

select * from matched
