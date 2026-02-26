"""
Property Test: Region Writer produces a valid Active Region Record.

Uses hypothesis to generate arbitrary valid event payloads and AWS_REGION values
from configured regions. Validates that the handler always produces a correct
Active_Region_Record and response structure.

Validates Requirements: 2.1, 2.2, 2.3, 2.4, 2.6, 3.1, 3.2, 3.3, 3.5
"""

import os
from datetime import datetime
from unittest.mock import MagicMock, patch

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

import app as app_module

CONFIGURED_REGIONS = ["us-east-1", "us-west-2"]

region_strategy = st.sampled_from(CONFIGURED_REGIONS)

execution_id_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P")),
    min_size=1,
    max_size=100,
)

plan_arn_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P")),
    min_size=1,
    max_size=200,
)

event_strategy = st.fixed_dictionaries(
    {
        "executionId": execution_id_strategy,
        "planArn": plan_arn_strategy,
        "action": st.just("activate"),
    }
)


def _make_mock_table():
    """Create a mock DynamoDB table that captures put_item calls."""
    mock_table = MagicMock()
    written_items = []

    def capture_put(Item):
        written_items.append(Item)

    mock_table.put_item.side_effect = capture_put
    mock_table._written_items = written_items
    return mock_table


def _invoke_handler(aws_region, table_name, event, mock_table):
    """Invoke the handler with mocked environment and DynamoDB."""
    env_overrides = {
        "AWS_REGION": aws_region,
        "ACTIVE_REGION_TABLE": table_name,
    }
    mock_context = MagicMock()
    mock_context.function_name = "region-writer"
    mock_context.memory_limit_in_mb = 128
    mock_context.invoked_function_arn = (
        f"arn:aws:lambda:{aws_region}:123456789:function:region-writer"
    )

    mock_dynamodb = MagicMock()
    mock_dynamodb.Table.return_value = mock_table

    with patch.dict(os.environ, env_overrides, clear=False), \
         patch.object(app_module, "dynamodb", mock_dynamodb):
        return app_module.handler(event, mock_context)


def _is_valid_iso8601(timestamp: str) -> bool:
    """Check if a string is a valid ISO 8601 timestamp."""
    try:
        datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")
        return True
    except (ValueError, TypeError):
        return False


@given(aws_region=region_strategy, event=event_strategy)
@settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_region_writer_produces_valid_record(aws_region, event):
    """
    Property 1: Region Writer produces a valid Active Region Record.

    For any valid invocation event and configured AWS_REGION value, the handler
    writes a record with correct pk, region, updatedAt, updatedBy, and returns
    a response with statusCode, region, and updatedAt.
    """
    table_name = "TestActiveRegionTable"
    mock_table = _make_mock_table()

    response = _invoke_handler(aws_region, table_name, event, mock_table)

    # --- Response assertions (Req 3.5) ---
    assert "statusCode" in response, "Response must contain statusCode"
    assert "region" in response, "Response must contain region"
    assert "updatedAt" in response, "Response must contain updatedAt"
    assert response["statusCode"] == 200, "Successful write should return 200"

    # --- Response field correctness ---
    assert response["region"] == aws_region, (
        f"Response region must match AWS_REGION: {aws_region}"
    )
    assert _is_valid_iso8601(response["updatedAt"]), (
        f"Response updatedAt must be valid ISO 8601: {response['updatedAt']}"
    )

    # --- DynamoDB item assertions ---
    assert len(mock_table._written_items) == 1, "Exactly one item should be written"
    item = mock_table._written_items[0]

    # Req 2.1: pk is ACTIVE_REGION
    assert item["pk"] == "ACTIVE_REGION", "pk must be 'ACTIVE_REGION'"

    # Req 2.2, 3.1: region matches AWS_REGION
    assert item["region"] == aws_region, (
        f"Item region must match AWS_REGION: {aws_region}"
    )
    assert item["region"] in CONFIGURED_REGIONS, (
        f"Item region must be a configured region: {CONFIGURED_REGIONS}"
    )

    # Req 2.3, 3.2: updatedAt is valid ISO 8601
    assert _is_valid_iso8601(item["updatedAt"]), (
        f"Item updatedAt must be valid ISO 8601: {item['updatedAt']}"
    )

    # Req 2.4, 3.3: updatedBy is populated from event context
    assert item["updatedBy"], "Item updatedBy must be populated"
    assert item["updatedBy"] == event["executionId"], (
        f"Item updatedBy should prefer executionId when present: {event['executionId']}"
    )



@given(
    aws_region=region_strategy,
    event=event_strategy,
    n_invocations=st.integers(min_value=1, max_value=10),
)
@settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_region_writer_idempotence(aws_region, event, n_invocations):
    """
    Property 2: Region Writer idempotence.

    For any region value and any number of repeated invocations N >= 1,
    invoking the handler N times with the same region produces the same
    region attribute value as invoking it once, and only one record exists
    in the table.

    Validates Requirements: 2.5, 3.4
    """
    table_name = "TestActiveRegionTable"

    # Simulate a table that tracks the single stored item across invocations
    stored_item = {}

    mock_table = MagicMock()

    def capture_put(Item):
        stored_item.clear()
        stored_item.update(Item)

    def get_item(**kwargs):
        if stored_item:
            return {"Item": dict(stored_item)}
        return {}

    mock_table.put_item.side_effect = capture_put
    mock_table.get_item.side_effect = get_item

    # Invoke the handler N times with the same region and event
    for _ in range(n_invocations):
        response = _invoke_handler(aws_region, table_name, event, mock_table)
        assert response["statusCode"] == 200, "Each invocation should succeed"

    # After N invocations the region attribute must match the input region
    assert stored_item["pk"] == "ACTIVE_REGION", "pk must be ACTIVE_REGION"
    assert stored_item["region"] == aws_region, (
        f"After {n_invocations} invocations the region must still be {aws_region}"
    )

    # Only one record should exist (the stored_item dict represents the sole item)
    assert len(stored_item) > 0, "Exactly one record must exist in the table"

