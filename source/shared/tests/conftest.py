"""Pytest configuration for shared module tests."""

import os
import sys
from pathlib import Path

# Set environment variables BEFORE any module imports to satisfy boto3 and Powertools
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ["AWS_REGION"] = "us-east-1"
os.environ["POWERTOOLS_TRACE_DISABLED"] = "true"
os.environ["POWERTOOLS_SERVICE_NAME"] = "active-region-reader"
os.environ["POWERTOOLS_METRICS_NAMESPACE"] = "test"

# Add the shared source directory to sys.path so 'active_region_reader' can be imported
_source_dir = Path(__file__).resolve().parent.parent
if str(_source_dir) not in sys.path:
    sys.path.insert(0, str(_source_dir))
