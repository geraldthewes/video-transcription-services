"""
Test configuration and shared fixtures for the transcription service.
"""
import asyncio
import json
import os
import tempfile
import uuid
from io import BytesIO
from typing import AsyncGenerator, Dict, Any
from unittest.mock import Mock, patch, AsyncMock

import pytest
import httpx
from fastapi.testclient import TestClient
from pytest_httpx import HTTPXMock

# Mock the cache directory before importing the app
with patch('os.makedirs'):
    with patch('transcriber_service.app.main.CACHE_DIR', '/tmp/test_cache'):
        # Import the FastAPI app
        from transcriber_service.app.main import app


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
async def async_client():
    """Create an async test client for the FastAPI app."""
    async with httpx.AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    with patch('transcriber_service.app.main.redis_client') as mock:
        mock_instance = Mock()
        mock_instance.ping.return_value = True
        mock_instance.get.return_value = None
        mock_instance.set.return_value = True
        mock_instance.delete.return_value = True
        mock_instance.keys.return_value = []
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_celery():
    """Mock Celery task."""
    with patch('transcriber_service.app.main.transcribe_audio_task') as mock_task:
        mock_result = Mock()
        mock_result.id = "test-celery-task-id"
        mock_task.delay.return_value = mock_result
        yield mock_task


@pytest.fixture
def mock_s3():
    """Mock S3 client and operations."""
    with patch('transcriber_service.app.main.create_s3_client') as mock_create:
        mock_client = Mock()
        mock_client.download_file.return_value = None
        mock_client.upload_file.return_value = None
        mock_create.return_value = mock_client
        yield mock_client


@pytest.fixture
def sample_task_metadata():
    """Sample task metadata for testing."""
    return {
        "client_id": "test-client",
        "status": "COMPLETED",
        "s3_results_path": None,
        "original_filename": "test.wav",
        "saved_filename": "test-task-id_test.wav",
        "upload_time": "2024-01-01T00:00:00",
        "task_type": "file_upload",
        "transcribed_json_file": "test-task-id/output.json",
        "transcribed_md_file": "test-task-id/output.md"
    }


@pytest.fixture
def sample_wav_file():
    """Create a sample WAV file for testing."""
    # Create a minimal WAV file header
    wav_header = b'RIFF' + b'\x24\x08\x00\x00' + b'WAVE' + b'fmt ' + b'\x10\x00\x00\x00' + \
                 b'\x01\x00\x01\x00\x44\xAC\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00' + \
                 b'data' + b'\x00\x08\x00\x00'
    # Add some sample audio data
    wav_data = b'\x00' * 2048
    return BytesIO(wav_header + wav_data)


@pytest.fixture
def sample_transcription_result():
    """Sample transcription result."""
    return {
        "transcript": "This is a test transcription",
        "segments": [
            {
                "start": 0.0,
                "end": 5.0,
                "text": "This is a test transcription",
                "topic": "general"
            }
        ],
        "metadata": {
            "duration": 5.0,
            "language": "en",
            "confidence": 0.95
        }
    }


@pytest.fixture
def temp_cache_dir():
    """Create a temporary cache directory for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        with patch('transcriber_service.app.main.CACHE_DIR', temp_dir):
            yield temp_dir


@pytest.fixture
def mock_environment():
    """Mock environment variables."""
    env_vars = {
        'REDIS_HOST': 'localhost',
        'REDIS_PORT': '6379',
        'OLLAMA_HOST': 'http://localhost:11434',
        'S3_STORAGE_BUCKET': 'test-bucket',
        'AWS_ACCESS_KEY_ID': 'test-access-key',
        'AWS_SECRET_ACCESS_KEY': 'test-secret-key',
        'AWS_REGION': 'us-east-1'
    }
    
    with patch.dict(os.environ, env_vars):
        yield env_vars


@pytest.fixture
def client_headers():
    """Standard client headers for requests."""
    return {"client_id": "test-client-123"}


@pytest.fixture
def httpx_mock():
    """HTTPx mock for external HTTP requests."""
    with HTTPXMock() as mock:
        yield mock


class MockAsyncContextManager:
    """Mock async context manager for httpx requests."""
    def __init__(self, response_data, status_code=200, headers=None):
        self.response_data = response_data
        self.status_code = status_code
        self.headers = headers or {}
    
    async def __aenter__(self):
        mock_response = Mock()
        mock_response.content = self.response_data
        mock_response.status_code = self.status_code
        mock_response.headers = self.headers
        mock_response.raise_for_status.return_value = None
        return mock_response
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


@pytest.fixture
def mock_httpx_client():
    """Mock httpx AsyncClient for external requests."""
    def _mock_client():
        mock_client = AsyncMock()
        mock_client.get = AsyncMock()
        return mock_client
    return _mock_client