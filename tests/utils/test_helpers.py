"""
Test utilities and helper functions.
"""
import io
import json
import tempfile
import uuid
from typing import Dict, Any, Optional

import pytest


class TestDataFactory:
    """Factory for creating test data."""
    
    @staticmethod
    def create_wav_file(duration_seconds: float = 1.0, sample_rate: int = 44100) -> io.BytesIO:
        """Create a minimal valid WAV file for testing."""
        # WAV file header (44 bytes)
        chunk_id = b'RIFF'
        chunk_size = (duration_seconds * sample_rate * 2 + 36).to_bytes(4, 'little')
        format_type = b'WAVE'
        subchunk1_id = b'fmt '
        subchunk1_size = (16).to_bytes(4, 'little')
        audio_format = (1).to_bytes(2, 'little')  # PCM
        num_channels = (1).to_bytes(2, 'little')  # Mono
        sample_rate_bytes = sample_rate.to_bytes(4, 'little')
        byte_rate = (sample_rate * 1 * 2).to_bytes(4, 'little')
        block_align = (2).to_bytes(2, 'little')
        bits_per_sample = (16).to_bytes(2, 'little')
        subchunk2_id = b'data'
        subchunk2_size = (duration_seconds * sample_rate * 2).to_bytes(4, 'little')
        
        # Assemble header
        header = (chunk_id + chunk_size + format_type + subchunk1_id + 
                 subchunk1_size + audio_format + num_channels + 
                 sample_rate_bytes + byte_rate + block_align + 
                 bits_per_sample + subchunk2_id + subchunk2_size)
        
        # Generate simple sine wave data
        data_size = int(duration_seconds * sample_rate * 2)
        data = b'\x00' * data_size  # Simple silence for testing
        
        return io.BytesIO(header + data)
    
    @staticmethod
    def create_task_metadata(
        task_id: Optional[str] = None,
        client_id: str = "test-client",
        status: str = "COMPLETED",
        s3_results_path: Optional[str] = None,
        task_type: str = "file_upload",
        **kwargs
    ) -> Dict[str, Any]:
        """Create task metadata for testing."""
        if task_id is None:
            task_id = str(uuid.uuid4())
        
        metadata = {
            "client_id": client_id,
            "status": status,
            "s3_results_path": s3_results_path,
            "original_filename": "test.wav",
            "saved_filename": f"{task_id}_test.wav",
            "upload_time": "2024-01-01T00:00:00",
            "task_type": task_type,
            "transcribed_json_file": f"{task_id}/output.json",
            "transcribed_md_file": f"{task_id}/output.md"
        }
        
        # Add any additional metadata
        metadata.update(kwargs)
        return metadata
    
    @staticmethod
    def create_transcription_result(
        text: str = "This is a test transcription",
        duration: float = 5.0,
        confidence: float = 0.95
    ) -> Dict[str, Any]:
        """Create a sample transcription result."""
        return {
            "transcript": text,
            "segments": [
                {
                    "start": 0.0,
                    "end": duration,
                    "text": text,
                    "topic": "general",
                    "confidence": confidence
                }
            ],
            "metadata": {
                "duration": duration,
                "language": "en",
                "confidence": confidence,
                "processing_time": 2.5
            }
        }


class ApiTestClient:
    """Helper class for making API requests in tests."""
    
    def __init__(self, client, default_client_id: str = "test-client"):
        self.client = client
        self.default_client_id = default_client_id
    
    def get_headers(self, client_id: Optional[str] = None) -> Dict[str, str]:
        """Get standard headers for requests."""
        return {"client_id": client_id or self.default_client_id}
    
    async def transcribe_file(
        self,
        file_content: io.BytesIO,
        filename: str = "test.wav",
        content_type: str = "audio/wav",
        s3_results_path: Optional[str] = None,
        client_id: Optional[str] = None
    ):
        """Helper for /transcribe endpoint."""
        files = {"file": (filename, file_content, content_type)}
        data = {}
        if s3_results_path:
            data["s3_results_path"] = s3_results_path
        
        return await self.client.post(
            "/transcribe",
            files=files,
            data=data,
            headers=self.get_headers(client_id)
        )
    
    async def transcribe_url(
        self,
        url: str,
        s3_results_path: Optional[str] = None,
        client_id: Optional[str] = None
    ):
        """Helper for /transcribe_url endpoint."""
        payload = {"url": url}
        if s3_results_path:
            payload["s3_results_path"] = s3_results_path
        
        return await self.client.post(
            "/transcribe_url",
            json=payload,
            headers=self.get_headers(client_id)
        )
    
    async def transcribe_s3(
        self,
        s3_input_path: str,
        s3_results_path: Optional[str] = None,
        client_id: Optional[str] = None
    ):
        """Helper for /transcribe_s3 endpoint."""
        payload = {"s3_input_path": s3_input_path}
        if s3_results_path:
            payload["s3_results_path"] = s3_results_path
        
        return await self.client.post(
            "/transcribe_s3",
            json=payload,
            headers=self.get_headers(client_id)
        )
    
    async def get_status(self, task_id: str, client_id: Optional[str] = None):
        """Helper for /status/{task_id} endpoint."""
        return await self.client.get(
            f"/status/{task_id}",
            headers=self.get_headers(client_id)
        )
    
    async def download_result(
        self,
        task_id: str,
        format_type: str = "json",
        client_id: Optional[str] = None
    ):
        """Helper for /download/{task_id} endpoint."""
        return await self.client.get(
            f"/download/{task_id}?fmt={format_type}",
            headers=self.get_headers(client_id)
        )
    
    async def release_task(self, task_id: str, client_id: Optional[str] = None):
        """Helper for /release/{task_id} endpoint."""
        return await self.client.delete(
            f"/release/{task_id}",
            headers=self.get_headers(client_id)
        )


@pytest.fixture
def test_data_factory():
    """Provide test data factory."""
    return TestDataFactory()


@pytest.fixture
def api_client(async_client):
    """Provide API test client."""
    return ApiTestClient(async_client)


class FileSystemTestHelper:
    """Helper for file system operations in tests."""
    
    @staticmethod
    def create_test_files(cache_dir: str, task_metadata: Dict[str, Any]):
        """Create test files referenced in task metadata."""
        import os
        
        files_created = []
        
        # Create saved audio file
        if task_metadata.get("saved_filename"):
            file_path = os.path.join(cache_dir, task_metadata["saved_filename"])
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'wb') as f:
                f.write(b"fake audio data")
            files_created.append(file_path)
        
        # Create transcribed JSON file
        if task_metadata.get("transcribed_json_file"):
            file_path = os.path.join(cache_dir, task_metadata["transcribed_json_file"])
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            result = TestDataFactory.create_transcription_result()
            with open(file_path, 'w') as f:
                json.dump(result, f)
            files_created.append(file_path)
        
        # Create transcribed Markdown file
        if task_metadata.get("transcribed_md_file"):
            file_path = os.path.join(cache_dir, task_metadata["transcribed_md_file"])
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'w') as f:
                f.write("# Test Transcript\n\nThis is a test transcription.")
            files_created.append(file_path)
        
        return files_created
    
    @staticmethod
    def cleanup_test_files(file_paths):
        """Clean up test files."""
        import os
        for file_path in file_paths:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except OSError:
                pass  # Ignore cleanup errors


@pytest.fixture
def fs_helper():
    """Provide file system test helper."""
    return FileSystemTestHelper()


def assert_valid_task_response(response_data: Dict[str, Any]):
    """Assert that a task creation response is valid."""
    assert "task_id" in response_data
    task_id = response_data["task_id"]
    assert isinstance(task_id, str)
    assert len(task_id) > 0
    # Validate UUID format
    uuid.UUID(task_id)  # This will raise ValueError if invalid


def assert_valid_health_response(response_data: Dict[str, Any]):
    """Assert that a health response is valid."""
    required_services = ["fastapi", "redis", "ollama", "celery"]
    for service in required_services:
        assert service in response_data
        assert isinstance(response_data[service], str)


def assert_valid_status_response(response_data: Dict[str, Any], expected_task_id: str):
    """Assert that a status response is valid."""
    assert response_data["task_id"] == expected_task_id
    assert "status" in response_data
    assert "details" in response_data
    assert isinstance(response_data["details"], dict)


def assert_valid_queue_response(response_data: Dict[str, Any]):
    """Assert that a queue response is valid."""
    assert "active_tasks_in_queue" in response_data
    assert "total_tracked_tasks" in response_data
    assert isinstance(response_data["active_tasks_in_queue"], int)
    assert isinstance(response_data["total_tracked_tasks"], int)
    assert response_data["active_tasks_in_queue"] >= 0
    assert response_data["total_tracked_tasks"] >= 0
    assert response_data["active_tasks_in_queue"] <= response_data["total_tracked_tasks"]