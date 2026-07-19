select *
from {{ ref('wallet_events') }}
where
  (transaction_from_address is null and (
    transaction_sender_relation != 'unknown' or is_indirect is not null
  ))
  or (transaction_from_address is not null and (
    transaction_sender_relation = 'unknown'
    or is_indirect != (transaction_from_address != from_address)
  ))
  or (transaction_to_address is null and transaction_target_relation != 'unknown')
  or (transaction_to_address is not null and transaction_target_relation = 'unknown')
