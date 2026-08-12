#!/usr/bin/env python3
"""Generate the checked-in synthetic Transfer-event fixture deterministically."""

from __future__ import annotations

import argparse
import csv
import io
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = ROOT / "analytics" / "seeds" / "raw_transfer_events_fixture.csv"
FIXTURE_WALLET_ADDRESS = "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
MAX_UINT256 = 2**256 - 1

COLUMNS: tuple[str, ...] = (
    "chain_id",
    "block_number",
    "block_hash",
    "block_timestamp",
    "transaction_hash",
    "transaction_index",
    "transaction_from_address",
    "transaction_to_address",
    "log_index",
    "token_address",
    "from_address",
    "to_address",
    "value_raw",
)

TOKENS = (
    ("0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", 6),
    ("0x6b175474e89094c44da98b954eedeac495271d0f", 18),
    ("0xdac17f958d2ee523a2206206994597c13d831ec7", 6),
    ("0x514910771af9ca656af840dff83e8264ecf986ca", 18),
    ("0x9999999999999999999999999999999999999999", 6),
)


def synthetic_address(prefix: str, number: int) -> str:
    return f"0x{prefix}{number:039x}"


COUNTERPARTIES = tuple(synthetic_address("2", number) for number in range(1, 13))
TRANSACTION_ACTORS = tuple(synthetic_address("3", number) for number in range(1, 9))


def fixture_datetimes() -> list[datetime]:
    dates: list[datetime] = []
    for year in range(2022, 2026):
        for month in range(1, 11):
            for day in (5, 19):
                dates.append(datetime(year, month, day, 12, tzinfo=timezone.utc))

    dates.extend(
        datetime(2026, month, day, 12, tzinfo=timezone.utc)
        for month, day in (
            (1, 5), (1, 19), (2, 5), (2, 19), (3, 5), (3, 19),
            (4, 5), (4, 19), (5, 5), (5, 19), (6, 5), (6, 19),
            (7, 5), (7, 10), (7, 15), (7, 20), (7, 25), (7, 28),
            (7, 29), (7, 30),
        )
    )
    return dates


def fixture_rows() -> list[dict[str, str | int]]:
    rows: list[dict[str, str | int]] = []
    for index, event_time in enumerate(fixture_datetimes()):
        token_address, decimals = TOKENS[index % len(TOKENS)]
        counterparty = COUNTERPARTIES[index % len(COUNTERPARTIES)]
        transaction_actor = TRANSACTION_ACTORS[index % len(TRANSACTION_ACTORS)]
        cycle_position = index % 20

        if cycle_position == 19:
            from_address = FIXTURE_WALLET_ADDRESS
            to_address = FIXTURE_WALLET_ADDRESS
            transaction_from_address = FIXTURE_WALLET_ADDRESS
        elif cycle_position == 4:
            from_address = ZERO_ADDRESS
            to_address = FIXTURE_WALLET_ADDRESS
            transaction_from_address = transaction_actor
        elif cycle_position == 14:
            from_address = FIXTURE_WALLET_ADDRESS
            to_address = ZERO_ADDRESS
            transaction_from_address = FIXTURE_WALLET_ADDRESS
        elif index % 2 == 0:
            from_address = counterparty
            to_address = FIXTURE_WALLET_ADDRESS
            transaction_from_address = (
                "" if index % 6 == 0
                else transaction_actor if index % 6 in (1, 2)
                else from_address
            )
        else:
            from_address = FIXTURE_WALLET_ADDRESS
            to_address = counterparty
            transaction_from_address = (
                "" if index % 6 == 0
                else transaction_actor if index % 6 in (1, 2)
                else from_address
            )

        if index == 8:
            transaction_from_address = to_address

        transaction_to_address = (
            "" if not transaction_from_address and index % 12 == 0
            else token_address if index % 4 == 0
            else to_address if index % 4 == 1
            else transaction_actor if index % 4 == 2
            else from_address
        )
        value_raw = (
            MAX_UINT256
            if index == 94
            else (index + 1) * 10**decimals + (index + 1) * 97
        )
        block_number = 14_000_001 + index * 13_000_000 // 99

        rows.append(
            {
                "chain_id": 1,
                "block_number": block_number,
                "block_hash": f"0x{0xB100000 + index:064x}",
                "block_timestamp": int(event_time.timestamp()) + (index % 8) * 3600,
                "transaction_hash": f"0x{0xA100000 + index:064x}",
                "transaction_index": index % 16,
                "transaction_from_address": transaction_from_address,
                "transaction_to_address": transaction_to_address,
                "log_index": index % 3,
                "token_address": token_address,
                "from_address": from_address,
                "to_address": to_address,
                "value_raw": value_raw,
            }
        )
    return rows


def render_fixture_csv() -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(fixture_rows())
    return output.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Fail when the checked-in seed differs")
    mode.add_argument("--write", action="store_true", help="Rewrite the checked-in seed")
    arguments = parser.parse_args()
    rendered = render_fixture_csv()

    if arguments.check:
        if SEED_PATH.read_text() != rendered:
            print(f"{SEED_PATH} is stale; run this command with --write", file=sys.stderr)
            return 1
        return 0
    if arguments.write:
        SEED_PATH.write_text(rendered)
        return 0

    sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
