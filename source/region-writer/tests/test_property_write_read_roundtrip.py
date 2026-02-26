"""
Property Test: Write-read round trip.

Uses hypothesis to generate valid region values, write via Region Writer,
read via Active Region Reader, and assert the region returned by the reader
matches the region written.

Validates Requirements: 3.1, 6.2
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

# Ensure the shared module is importable
_shared_dir = Path(__file__).resolve().parent.parent.parent / "shared"
if str(_shared_dir.parent) not in sys.path:
    sys.path.insert(0, str(_shared_dir.parent))

import app as app_module
import shared.active_region_reader as reader_module

CONFIGURED_REGIONS = ["us-east-1", "us-west-2"]

region_strategy = st.sampled_from(CONFIGURED_REGIONS)

execution_id_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P")),
    min_size=1,
    max_size=100,
)

event_strategy = st.fixed_dictionaries(
    {
        "executionId": execution_id_strategy,
        "planArn": st.just("arn:aws:arc-region-switch:us-east-1:123456789:plan/test"),
        "action": st.just("activate"),
    }
)


def _build_shared_table():
    """Build a mock DynamoDB table that stores items in memory so both
    the writer and reader operate on the same state."""
    store = {}
    mock_table = MagicMock()

    def put_item(Item):
        store[Item["pk"]] = dict(Item)

    def get_item(Key=None, ConsistentRead=None, **kwargs):
        # Support both keyword styles used by writer and reader
        key = Key or kwargs.get("Key")
        pk = key["pk"] if key else None
        item = store.get(pk)
        if item:
            return {"Item": dict(item)}
        return {}

    mock_table.put_item.side_effect = put_item
    mock_table.get_item.side_effect = get_item
    mock_table._store = store
    return mock_table


@given(aws_region=region_strategy, event=event_strategy)
@settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_write_read_roundtrip(aws_region, event):
    """
    Property 3: Write-read round trip.

    For any valid region written by the Region Writer Lambda, reading the
    Active_Region_Record via the Active Region Reader returns the same
    region string that was written.
    """
    table_name = "TestActiveRegionTable"
    mock_table = _build_shared_table()

    # --- Write phase: invoke Region Writer ---
    mock_dynamodb_writer = MagicMock()
    mock_dynamodb_writer.Table.return_value = mock_table

    mock_context = MagicMock()
    mock_context.function_name = "region-writer"
    mock_context.memory_limit_in_mb = 128
    mock_context.invoked_function_arn = (
        f"arn:aws:lambda:{aws_region}:123456789:function:region-writer"
    )

    env_overrides = {
        "AWS_REGION": aws_region,
        "ACTIVE_REGION_TABLE": table_name,
    }

    with patch.dict(os.environ, env_overrides, clear=False), \
         patch.object(app_module, "dynamodb", mock_dynamodb_writer):
        write_response = app_module.handler(event, mock_context)

    assert write_response["statusCode"] == 200, "Write must succeed"

    # --- Read phase: invoke Active Region Reader ---
    mock_dynamodb_reader = MagicMock()
    mock_dynamodb_reader.Table.return_value = mock_table

    with patch.object(reader_module, "dynamodb", mock_dynamodb_reader):
        read_region = reader_module.get_active_region(table_name)

    # --- Round-trip assertion ---
    assert read_region == aws_region, (
        f"Reader must return the same region that was written. "
        f"Wrote: {aws_region}, Read: {read_region}"
    )
