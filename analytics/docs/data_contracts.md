{% docs transfer_signature_scope %}
Rows originate from logs matching `Transfer(address,address,uint256)`. The signature is
ERC-20-intended in this project but is also emitted by ERC-721 contracts, so it does not by
itself prove token standard, fungibility, intent, ownership, or economic value.
{% enddocs %}

{% docs canonical_event_identity %}
Canonical event identity is `(chain_id, transaction_hash, log_index)`. A configured-wallet
delivery relation adds `wallet_address` to its grain because direction and counterparty are
defined relative to that wallet.
{% enddocs %}

{% docs exact_raw_value %}
Exact base-10 string emitted as the log's third value. It is never converted to floating point.
Token decimals are separate, sourced metadata and do not change this evidence.
{% enddocs %}

{% docs token_recognition %}
Automatic exact-contract-address classification. `recognized` means the address appeared in a
selected registry or reviewed seed; `other` means no such match was recorded. This is time-varying
evidence, not a safety or legitimacy judgment. Application-owned overrides are applied later by
the local API and do not alter dbt relations.
{% enddocs %}

{% docs account_type %}
Point-in-time classification from pinned-block bytecode evidence. `eoa_candidate` means no
ordinary contract bytecode was observed, `contract` means bytecode was observed, and `unknown`
means no successful classification is available. It does not prove personhood, control,
permanence, or historical type.
{% enddocs %}

{% docs code_state %}
Pinned-block bytecode state supporting account classification: `no_code`,
`eip7702_delegated`, `contract_code`, or `unknown`.
{% enddocs %}

{% docs direction %}
Direction relative to the configured wallet. `self` is assigned first when both emitted
participants equal the wallet; otherwise `in` means the wallet is the recipient and `out` means
the wallet is the sender.
{% enddocs %}

{% docs finalized_snapshot %}
Live coverage comes from one completed contiguous pipeline snapshot ending at a pinned Ethereum
finalized block and hash. Event minima and maxima describe observed events only and never prove
that intervening blocks were scanned.
{% enddocs %}

{% docs bounded_fixture %}
Deterministic fixture input used for tests and the static portfolio demo. It does not establish
HyperIndex coverage, live freshness, or production provenance.
{% enddocs %}
