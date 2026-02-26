"""
Unit tests for Region Writer error handling.

Tests:
- DynamoDB write failure triggers retry with exponential backoff
- All retries exhausted returns error response
- Exception logging includes exception type and table name

Validates Requirements: 4.1, 4.2, 4.3
"""

import os
from unittest.mock import MagicMock, patch, call

from botocore.exceptions import ClientError

import app as app_module


TABLE_NAME = "TestActiveRegionTable"
REGION = "us-east-1"
EVENT = {"executionId": "exec-123", "planArn": "arn:aws:arc:us-east-1:123:plan/test", "action": "activate"}


def _make_context():
    ctx = MagicMock()
    ctx.function_name = "region-writer"
    ctx.memory_limit_in_mb = 128
    ctx.invoked_function_arn = f"arn:aws:lambda:{REGION}:123456789:function:region-writer"
    return ctx


def _client_error(code="InternalServerError", message="Service unavailable"):
    return ClientError(
        {"Error": {"Code": code, "Message": message}},
        "PutItem",
    )


def _invoke(mock_table, mock_sleep=None):
    """Invoke the handler with a mocked DynamoDB table and optional sleep mock."""
    mock_dynamodb = MagicMock()
    mock_dynamodb.Table.return_value = mock_table

    env = {"AWS_REGION": REGION, "ACTIVE_REGION_TABLE": TABLE_NAME}

    patches = [
        patch.dict(os.environ, env, clear=False),
        patch.object(app_module, "dynamodb", mock_dynamodb),
    ]
    if mock_sleep is not None:
        patches.append(patch("app.time.sleep", mock_sleep))

    with patches[0], patches[1], (patches[2] if len(patches) == 3 else patch("app.time.sleep", MagicMock())) as sleep_mock:
        if mock_sleep is None:
            mock_sleep = sleep_mock
        return app_module.handler(EVENT, _make_context()), mock_sleep


class TestRetryWithExponentialBackoff:
    """Req 4.1: DynamoDB write failure triggers retry with exponential backoff."""

    def test_transient_failure_retries_then_succeeds(self):
        """A transient failure on the first attempt should retry and succeed on the second."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}
        mock_table.put_item.side_effect = [
            _client_error(),  # attempt 1 fails
            None,             # attempt 2 succeeds
        ]

        response, sleep_mock = _invoke(mock_table)

        assert response["statusCode"] == 200
        assert response["region"] == REGION
        assert mock_table.put_item.call_count == 2
        # Backoff after first failure: 2^(1-1) = 1 second
        sleep_mock.assert_called_once_with(1)

    def test_two_failures_then_success(self):
        """Two transient failures should retry twice with increasing backoff, then succeed."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}
        mock_table.put_item.side_effect = [
            _client_error(),  # attempt 1 fails
            _client_error(),  # attempt 2 fails
            None,             # attempt 3 succeeds
        ]

        response, sleep_mock = _invoke(mock_table)

        assert response["statusCode"] == 200
        assert mock_table.put_item.call_count == 3
        # Backoff: 2^0=1s after attempt 1, 2^1=2s after attempt 2
        assert sleep_mock.call_args_list == [call(1), call(2)]

    def test_no_sleep_on_first_attempt(self):
        """A successful first attempt should not trigger any sleep."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}
        mock_table.put_item.return_value = None

        response, sleep_mock = _invoke(mock_table)

        assert response["statusCode"] == 200
        assert mock_table.put_item.call_count == 1
        sleep_mock.assert_not_called()


class TestAllRetriesExhausted:
    """Req 4.2: All retries exhausted returns error response."""

    def test_three_failures_returns_error(self):
        """Three consecutive failures should exhaust retries and return 500."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}
        mock_table.put_item.side_effect = _client_error()

        response, sleep_mock = _invoke(mock_table)

        assert response["statusCode"] == 500
        assert "error" in response
        assert "3" in response["error"]  # mentions attempt count
        assert response["region"] == REGION
        assert response["tableName"] == TABLE_NAME
        assert mock_table.put_item.call_count == 3

    def test_no_sleep_after_last_attempt(self):
        """After the final failed attempt, no additional sleep should occur."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}
        mock_table.put_item.side_effect = _client_error()

        _, sleep_mock = _invoke(mock_table)

        # Only 2 sleeps: after attempt 1 and attempt 2. No sleep after attempt 3.
        assert sleep_mock.call_count == 2


class TestErrorLogging:
    """Req 4.3: Exception logging includes exception type and table name."""

    def test_logs_exception_type_and_table_name_on_failure(self):
        """Each failed attempt should log the exception type and table name."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}
        mock_table.put_item.side_effect = _client_error("ProvisionedThroughputExceededException")

        with patch.object(app_module, "logger") as mock_logger:
            mock_dynamodb = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            env = {"AWS_REGION": REGION, "ACTIVE_REGION_TABLE": TABLE_NAME}

            with patch.dict(os.environ, env, clear=False), \
                 patch.object(app_module, "dynamodb", mock_dynamodb), \
                 patch("app.time.sleep"):
                app_module.handler(EVENT, _make_context())

            # Should have logged an error for each of the 3 failed attempts
            assert mock_logger.error.call_count == 3

            for error_call in mock_logger.error.call_args_list:
                extra = error_call.kwargs.get("extra", {})
                assert extra["exceptionType"] == "ClientError"
                assert extra["tableName"] == TABLE_NAME

    def test_log_includes_attempt_number(self):
        """Each error log should include the current attempt number."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}
        mock_table.put_item.side_effect = _client_error()

        with patch.object(app_module, "logger") as mock_logger:
            mock_dynamodb = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            env = {"AWS_REGION": REGION, "ACTIVE_REGION_TABLE": TABLE_NAME}

            with patch.dict(os.environ, env, clear=False), \
                 patch.object(app_module, "dynamodb", mock_dynamodb), \
                 patch("app.time.sleep"):
                app_module.handler(EVENT, _make_context())

            for i, error_call in enumerate(mock_logger.error.call_args_list, start=1):
                extra = error_call.kwargs.get("extra", {})
                assert extra["attempt"] == i
                assert extra["maxAttempts"] == 3
