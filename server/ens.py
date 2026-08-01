"""Safe, finalized-block ENS input resolution for scan jobs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from eth_hash.auto import keccak

CHAIN_ID = 1
ENS_REGISTRY_ADDRESS = "0x00000000000c2e074ec69a0dfb2997ba6c7d2e1e"
ENS_RESOLVER_SOURCE = f"ens-registry:{ENS_REGISTRY_ADDRESS}"
FINALITY_POLICY = "ethereum_finalized"
ADDRESS_PATTERN = re.compile(r"^0x[0-9a-fA-F]{40}$")
LABEL_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
HASH_PATTERN = re.compile(r"^0x[0-9a-f]{64}$")
ZERO_ADDRESS = "0x" + "0" * 40


class ENSNotRecognizedError(ValueError):
    """The scan input is not a supported address or resolvable ENS name."""


class ENSRpc(Protocol):
    def call(self, method: str, params: list[Any]) -> Any: ...


@dataclass(frozen=True)
class FinalizedObservation:
    block_number: int
    block_hash: str
    observed_at: datetime


@dataclass(frozen=True)
class ResolvedScanInput:
    original_input: str
    normalized_name: str | None
    resolved_address: str
    resolver_source: str
    observation_block_number: int
    observation_block_hash: str
    observed_at: datetime


def normalize_address(value: str) -> str | None:
    if ADDRESS_PATTERN.fullmatch(value.strip()):
        return value.strip().lower()
    return None


def normalize_ens_name(value: str) -> str:
    """Return a conservative ASCII ENS name, rejecting lookalike Unicode input."""

    candidate = value.strip().rstrip(".").lower()
    if not candidate or len(candidate.encode("ascii", errors="ignore")) != len(candidate):
        raise ENSNotRecognizedError("ENS name is unsupported; use lowercase ASCII labels")
    if len(candidate) > 255 or any(not LABEL_PATTERN.fullmatch(label) for label in candidate.split(".")):
        raise ENSNotRecognizedError("ENS name is unsupported or malformed")
    return candidate


def namehash(name: str) -> bytes:
    node = b"\x00" * 32
    for label in reversed(name.split(".")):
        node = keccak(node + keccak(label.encode("utf-8")))
    return node


def _block_observation(client: ENSRpc) -> FinalizedObservation:
    block = client.call("eth_getBlockByNumber", ["finalized", False])
    if not isinstance(block, dict) or not block.get("number") or not block.get("hash") or not block.get("timestamp"):
        raise ENSNotRecognizedError("Ethereum RPC did not return a usable finalized observation block")
    block_hash = str(block["hash"]).lower()
    try:
        number = int(str(block["number"]), 16)
        timestamp = int(str(block["timestamp"]), 16)
    except ValueError as error:
        raise ENSNotRecognizedError("Ethereum RPC returned an invalid finalized observation block") from error
    if not HASH_PATTERN.fullmatch(block_hash):
        raise ENSNotRecognizedError("Ethereum RPC returned an invalid finalized observation hash")
    return FinalizedObservation(number, block_hash, datetime.fromtimestamp(timestamp, timezone.utc))


def _decode_address(value: Any) -> str | None:
    if not isinstance(value, str) or not value.startswith("0x"):
        return None
    try:
        raw = bytes.fromhex(value[2:])
    except ValueError:
        return None
    if len(raw) != 32:
        return None
    address = "0x" + raw[-20:].hex()
    return None if address == ZERO_ADDRESS else address


def resolve_scan_input(
    value: str,
    client: ENSRpc,
    *,
    observation: FinalizedObservation | None = None,
) -> ResolvedScanInput:
    """Resolve an address or ENS name once, at one Ethereum finalized block."""

    original = value.strip()
    if not original:
        raise ENSNotRecognizedError("ENS name is not recognized: input is empty")
    observed = observation or _block_observation(client)
    block_tag = hex(observed.block_number)
    address = normalize_address(original)
    if address is not None:
        return ResolvedScanInput(
            original, None, address, "direct-address", observed.block_number, observed.block_hash, observed.observed_at
        )

    normalized = normalize_ens_name(original)
    node = namehash(normalized).hex()
    resolver_result = client.call(
        "eth_call",
        [{"to": ENS_REGISTRY_ADDRESS, "data": "0x0178b8bf" + node}, block_tag],
    )
    resolver = _decode_address(resolver_result)
    if resolver is None:
        raise ENSNotRecognizedError(f"ENS name is not recognized: {normalized}")
    resolved = _decode_address(
        client.call("eth_call", [{"to": resolver, "data": "0x3b3b57de" + node}, block_tag])
    )
    if resolved is None:
        raise ENSNotRecognizedError(f"ENS name is not recognized: {normalized}")
    return ResolvedScanInput(
        original,
        normalized,
        resolved,
        f"{ENS_RESOLVER_SOURCE}/resolver:{resolver}",
        observed.block_number,
        observed.block_hash,
        observed.observed_at,
    )
