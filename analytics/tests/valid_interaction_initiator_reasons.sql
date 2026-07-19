select *
from {{ ref('int_wallet_token_interactions') }}
where indirect_inbound_transfer_count > inbound_transfer_count
  or indirect_outbound_transfer_count > outbound_transfer_count
  or interaction_legitimacy_reasons like '%mass_outbound_without_initiator_proof%'
  or (
    interaction_legitimacy_reasons like '%mass_outbound_transaction_sender_matches_wallet%'
    and (
      evidenced_outbound_transfer_count != outbound_transfer_count
      or sender_matched_outbound_transfer_count != outbound_transfer_count
    )
  )
