with expected as (
  select
    chain_id,
    wallet_address,
    count(distinct counterparty_address) as eligible_address_count,
    count(distinct counterparty_address) filter (
      where counterparty_evidence_fetch_status = 'complete'
    ) as classified_address_count,
    count(distinct counterparty_address) filter (
      where counterparty_evidence_fetch_status = 'failed'
    ) as failed_address_count,
    count(distinct counterparty_address) filter (
      where counterparty_evidence_fetch_status = 'not_fetched'
    ) as not_checked_address_count,
    count(*) as eligible_event_count,
    count(*) filter (
      where counterparty_evidence_fetch_status = 'complete'
    ) as classified_event_count,
    count(*) filter (
      where counterparty_evidence_fetch_status = 'failed'
    ) as failed_event_count,
    count(*) filter (
      where counterparty_evidence_fetch_status = 'not_fetched'
    ) as not_checked_event_count
  from {{ ref('int_wallet_transfer_events') }}
  where counterparty_address != '0x0000000000000000000000000000000000000000'
    and counterparty_address != wallet_address
  group by chain_id, wallet_address
)

select metadata.wallet_address
from {{ ref('pipeline_metadata') }} as metadata
left join expected using (chain_id, wallet_address)
where metadata.account_evidence_population_scope != 'distinct_nonzero_nonself_event_counterparties'
  or metadata.account_evidence_eligible_address_count != coalesce(expected.eligible_address_count, 0)
  or metadata.account_evidence_classified_address_count != coalesce(expected.classified_address_count, 0)
  or metadata.account_evidence_failed_address_count != coalesce(expected.failed_address_count, 0)
  or metadata.account_evidence_not_checked_address_count != coalesce(expected.not_checked_address_count, 0)
  or metadata.account_evidence_eligible_event_count != coalesce(expected.eligible_event_count, 0)
  or metadata.account_evidence_classified_event_count != coalesce(expected.classified_event_count, 0)
  or metadata.account_evidence_failed_event_count != coalesce(expected.failed_event_count, 0)
  or metadata.account_evidence_not_checked_event_count != coalesce(expected.not_checked_event_count, 0)
  or metadata.account_evidence_eligible_address_count
    != metadata.account_evidence_classified_address_count
      + metadata.account_evidence_failed_address_count
      + metadata.account_evidence_not_checked_address_count
  or metadata.account_evidence_eligible_event_count
    != metadata.account_evidence_classified_event_count
      + metadata.account_evidence_failed_event_count
      + metadata.account_evidence_not_checked_event_count
  or metadata.account_evidence_observation_block_number_min
    > metadata.account_evidence_observation_block_number_max
  or metadata.account_evidence_observation_block_timestamp_min
    > metadata.account_evidence_observation_block_timestamp_max
  or (
    metadata.account_evidence_classified_address_count = 0
    and (
      metadata.account_evidence_observation_block_number_min is not null
      or metadata.account_evidence_observation_block_number_max is not null
      or metadata.account_evidence_observation_block_timestamp_min is not null
      or metadata.account_evidence_observation_block_timestamp_max is not null
      or metadata.account_evidence_schema_version is not null
    )
  )
