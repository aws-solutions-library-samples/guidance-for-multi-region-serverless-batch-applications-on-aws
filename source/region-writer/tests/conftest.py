"""Pytest configuration for region-writer tests."""

import os
import sys
from pathlib import Path

# Set environment variables BEFORE any module imports to satisfy boto3 and Powertools
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ["AWS_REGION"] = "us-east-1"
os.environ["ACTIVE_REGION_TABLE"] = "TestActiveRegionTable"
os.environ["POWERTOOLS_TRACE_DISABLED"] = "true"
os.environ["POWERTOOLS_SERVICE_NAME"] = "region-writer"
os.environ["POWERTOOLS_METRICS_NAMESPACE"] = "test"

# Add the region-writer source directory to sys.path so 'app' can be imported
_source_dir = Path(__file__).resolve().parent.parent
if str(_source_dir) not in sys.path:
    sys.path.insert(0, str(_source_dir))
