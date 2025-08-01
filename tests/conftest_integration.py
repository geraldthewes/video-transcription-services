"""
Additional fixtures specifically for integration tests against real services.
"""
import asyncio
from pathlib import Path

import httpx
import pytest


# Integration test configuration
INTEGRATION_SERVICE_URL = "http://localhost:8000"
INTEGRATION_TIMEOUT = 60  # seconds
INTEGRATION_CLIENT_ID = "integration-test-client"


@pytest.fixture(scope="session")
async def integration_client():
    """HTTP client for integration tests against real service."""
    async with httpx.AsyncClient(
        base_url=INTEGRATION_SERVICE_URL,
        timeout=httpx.Timeout(timeout=INTEGRATION_TIMEOUT)
    ) as client:
        yield client


@pytest.fixture(scope="session")
async def service_available(integration_client):
    """Check if the service is available before running integration tests."""
    try:
        response = await integration_client.get("/health")
        if response.status_code == 200:
            return True
        else:
            pytest.skip(f"Service not healthy: HTTP {response.status_code}")
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        pytest.skip(f"Service not available at {INTEGRATION_SERVICE_URL}: {e}")
    return False


@pytest.fixture
def integration_headers():
    """Standard headers for integration tests."""
    return {"client_id": INTEGRATION_CLIENT_ID}


@pytest.fixture
def real_audio_file():
    """Path to real audio file for integration testing."""
    audio_path = Path("test_data/5rmAy8fgYsY_audio.wav")
    if not audio_path.exists():
        pytest.skip(f"Real audio file not found: {audio_path}")
    return audio_path


@pytest.fixture
def integration_test_config():
    """Configuration for integration tests."""
    return {
        "service_url": INTEGRATION_SERVICE_URL,
        "timeout": INTEGRATION_TIMEOUT,
        "client_id": INTEGRATION_CLIENT_ID,
        "max_transcription_wait": 300,  # 5 minutes
        "status_check_interval": 5,     # 5 seconds
    }