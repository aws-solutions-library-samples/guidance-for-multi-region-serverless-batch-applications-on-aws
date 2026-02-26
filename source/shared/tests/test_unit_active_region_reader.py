"""
Unit tests for Active Region Reader.

Tests:
- Successful read returns region string
- Missing record raises ActiveRegionNotFoundError and emits CloudWatch metric
- DynamoDB exception raises DynamoDBReadError with details

Validates Requirements: 6.1, 6.2, 6.3, 6.4
"""

from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

import active_region_reader as reader_module
from active_region_reader import (
    get_active_region,
    ActiveRegionNotFoundError,
    DynamoDBReadError,
)

TABLE_NAME = "TestActiveRegionTable"


def _client_error(code="InternalServerError", message="Service unavailable"):
    return ClientError(
        {"Error": {"Code": code, "Message": message}},
        "GetItem",
    )


def _mock_table_with_response(response):
    """Create a mock DynamoDB resource whose Table().get_item returns the given response."""
    mock_table = MagicMock()
    mock_table.get_item.return_value = response
    mock_dynamodb = MagicMock()
    mock_dynamodb.Table.return_value = mock_table
    return mock_dynamodb, mock_table


class TestSuccessfulRead:
    """Req 6.1, 6.2: Successful read returns region string."""

    def test_returns_region_string(self):
        mock_dynamodb, mock_table = _mock_table_with_response(
            {"Item": {"pk": "ACTIVE_REGION", "region": "us-east-1"}}
        )

        with patch.object(reader_module, "dynamodb", mock_dynamodb):
            result = get_active_region(TABLE_NAME)

        assert result == "us-east-1"

    def test_uses_consistent_read(self):
        mock_dynamodb, mock_table = _mock_table_with_response(
            {"Item": {"pk": "ACTIVE_REGION", "region": "us-west-2"}}
        )

        with patch.object(reader_module, "dynamodb", mock_dynamodb):
            get_active_region(TABLE_NAME)

        mock_table.get_item.assert_called_once_with(
            Key={"pk": "ACTIVE_REGION"},
            ConsistentRead=True,
        )

    def test_returns_secondary_region(self):
        mock_dynamodb, _ = _mock_table_with_response(
            {"Item": {"pk": "ACTIVE_REGION", "region": "us-west-2"}}
        )

        with patch.object(reader_module, "dynamodb", mock_dynamodb):
            result = get_active_region(TABLE_NAME)

        assert result == "us-west-2"


class TestMissingRecordRaisesNotFoundError:
    """Req 6.3: Missing record raises ActiveRegionNotFoundError and emits CloudWatch metric."""

    def test_raises_active_region_not_found_error(self):
        mock_dynamodb, _ = _mock_table_with_response({"Item": None})

        with patch.object(reader_module, "dynamodb", mock_dynamodb):
            try:
                get_active_region(TABLE_NAME)
                assert False, "Expected ActiveRegionNotFoundError"
            except ActiveRegionNotFoundError as exc:
                assert TABLE_NAME in str(exc)

    def test_raises_when_item_key_absent(self):
        """Response with no 'Item' key at all should also raise."""
        mock_dynamodb, _ = _mock_table_with_response({})

        with patch.object(reader_module, "dynamodb", mock_dynamodb):
            try:
                get_active_region(TABLE_NAME)
                assert False, "Expected ActiveRegionNotFoundError"
            except ActiveRegionNotFoundError:
                pass

    def test_emits_cloudwatch_metric_on_not_found(self):
        mock_dynamodb, _ = _mock_table_with_response({})

        with patch.object(reader_module, "dynamodb", mock_dynamodb), \
             patch.object(reader_module, "metrics") as mock_metrics:
            try:
                get_active_region(TABLE_NAME)
            except ActiveRegionNotFoundError:
                pass

            mock_metrics.add_metric.assert_called_once()
            call_kwargs = mock_metrics.add_metric.call_args
            assert call_kwargs.kwargs["name"] == "ActiveRegionNotFound"
            assert call_kwargs.kwargs["value"] == 1

    def test_logs_warning_on_not_found(self):
        mock_dynamodb, _ = _mock_table_with_response({})

        with patch.object(reader_module, "dynamodb", mock_dynamodb), \
             patch.object(reader_module, "logger") as mock_logger:
            try:
                get_active_region(TABLE_NAME)
            except ActiveRegionNotFoundError:
                pass

            mock_logger.warning.assert_called_once()
            extra = mock_logger.warning.call_args.kwargs.get("extra", {})
            assert extra["tableName"] == TABLE_NAME


class TestDynamoDBExceptionRaisesReadError:
    """Req 6.4: DynamoDB exception raises DynamoDBReadError with details."""

    def test_raises_dynamodb_read_error(self):
        mock_table = MagicMock()
        mock_table.get_item.side_effect = _client_error()
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table

        with patch.object(reader_module, "dynamodb", mock_dynamodb):
            try:
                get_active_region(TABLE_NAME)
                assert False, "Expected DynamoDBReadError"
            except DynamoDBReadError as exc:
                assert TABLE_NAME in str(exc)

    def test_wraps_original_exception(self):
        original = _client_error("ProvisionedThroughputExceededException", "Rate exceeded")
        mock_table = MagicMock()
        mock_table.get_item.side_effect = original
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table

        with patch.object(reader_module, "dynamodb", mock_dynamodb):
            try:
                get_active_region(TABLE_NAME)
                assert False, "Expected DynamoDBReadError"
            except DynamoDBReadError as exc:
                assert exc.__cause__ is original

    def test_logs_error_with_exception_type_and_table_name(self):
        mock_table = MagicMock()
        mock_table.get_item.side_effect = _client_error("ServiceUnavailable")
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table

        with patch.object(reader_module, "dynamodb", mock_dynamodb), \
             patch.object(reader_module, "logger") as mock_logger:
            try:
                get_active_region(TABLE_NAME)
            except DynamoDBReadError:
                pass

            mock_logger.error.assert_called_once()
            extra = mock_logger.error.call_args.kwargs.get("extra", {})
            assert extra["exceptionType"] == "ClientError"
            assert extra["tableName"] == TABLE_NAME
