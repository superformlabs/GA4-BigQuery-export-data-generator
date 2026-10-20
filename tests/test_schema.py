"""GEN-2: the schema the installed generator loads with is the agreed one.

The table schema is the file events.json inside the generator
(docs/contracts/ga4-export-schema.md). Two checks: the installed file matches
the column table written in the contract, and generated rows carry exactly
those columns, with each of the app's two configurations.

The first check needs the contract, which is a file of the app and not part of
the generator's public copy. Where docs/contracts/ is absent it skips and says
so; see contract_file() in conftest.py.
"""

from __future__ import annotations

import gzip
import json
import re
from pathlib import Path

import pytest

from conftest import (
    CONFIGURATIONS,
    FIXED_DATE,
    contract_file,
    installed_schema_file,
)

# The name of the contract, not its path: contract_file() resolves it and
# skips the test where docs/contracts/ is absent, which is the case in the
# public copy of the generator. The second test below needs no contract. It
# reads the installed schema itself, so it runs from that copy too.
SCHEMA_CONTRACT = "ga4-export-schema.md"


def field_paths(fields: list[dict]) -> int:
    return sum(1 + field_paths(field.get("fields", [])) for field in fields)


def contract_columns(contract: str) -> list[tuple[str, str, str]]:
    """The rows of the column table in the contract: name, type, mode."""
    rows = re.findall(
        r"^\| (\w+) \| (\S+(?: \(.*?\))?) \| (\w+) \|$",
        contract,
        re.MULTILINE,
    )
    return [row for row in rows if row[0] != "Column"]


def test_installed_schema_matches_the_contract() -> None:
    contract = contract_file(SCHEMA_CONTRACT).read_text(encoding="utf-8")
    schema = json.loads(installed_schema_file().read_text(encoding="utf-8"))

    counts = re.search(r"(\d+) top-level columns, (\d+) field paths", contract)
    assert counts, "the contract no longer states the number of columns"
    assert len(schema) == int(counts.group(1))
    assert field_paths(schema) == int(counts.group(2))

    columns = contract_columns(contract)
    assert [name for name, _, _ in columns] == [field["name"] for field in schema]
    for (name, kind, mode), field in zip(columns, schema):
        assert kind.split(" ")[0] == field["type"], name
        assert mode == field.get("mode", "NULLABLE"), name
        sub_fields = re.search(r"\((\d+) fields?\)", kind)
        if sub_fields:
            assert int(sub_fields.group(1)) == len(field["fields"]), name


@pytest.mark.parametrize("configuration", CONFIGURATIONS)
def test_generated_rows_carry_the_schema_columns(
    configuration: str, generated_shard: Callable[[str], Path]
) -> None:
    """Gzipped newline-delimited JSON, one row per line, every column present."""
    schema = json.loads(installed_schema_file().read_text(encoding="utf-8"))
    columns = [field["name"] for field in schema]
    event_date = FIXED_DATE.strftime("%Y%m%d")
    rows = 0
    with gzip.open(generated_shard(configuration), "rt", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            assert sorted(row) == sorted(columns)
            assert row["event_date"] == event_date
            rows += 1
    assert rows > 0
