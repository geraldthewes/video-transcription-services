"""
Integration tests for the complete API workflow.
"""
import json
import os
from unittest.mock import patch, Mock

import pytest

from tests.utils.test_helpers import (
    assert_valid_task_response,
    assert_valid_health_response,
    assert_valid_status_response,
    assert_valid_queue_response
)


@pytest.mark.integration
class TestCompleteWorkflow:
    """Test complete transcription workflow end-to-end."""

    async def test_file_upload_workflow(
        self,
        api_client,
        test_data_factory,
        mock_redis,
        mock_celery,
        temp_cache_dir,
        fs_helper
    ):
        """Test complete file upload and processing workflow."""
        # Step 1: Upload file for transcription
        wav_file = test_data_factory.create_wav_file(duration_seconds=2.0)
        
        response = await api_client.transcribe_file(wav_file, "test_audio.wav")
        assert response.status_code == 200
        
        data = response.json()
        assert_valid_task_response(data)
        task_id = data["task_id"]
        
        # Step 2: Check initial status
        task_metadata = test_data_factory.create_task_metadata(
            task_id=task_id,
            status="PENDING_CELERY_DISPATCH"
        )
        mock_redis.get.return_value = json.dumps(task_metadata)
        
        status_response = await api_client.get_status(task_id)
        assert status_response.status_code == 200
        assert_valid_status_response(status_response.json(), task_id)
        
        # Step 3: Simulate task completion
        task_metadata["status"] = "COMPLETED"
        mock_redis.get.return_value = json.dumps(task_metadata)
        
        # Create result files
        fs_helper.create_test_files(temp_cache_dir, task_metadata)
        
        # Step 4: Download results
        json_response = await api_client.download_result(task_id, "json")
        assert json_response.status_code == 200
        
        md_response = await api_client.download_result(task_id, "md")
        assert md_response.status_code == 200
        
        # Step 5: Release resources
        release_response = await api_client.release_task(task_id)
        assert release_response.status_code == 200
        
        release_data = release_response.json()
        assert release_data["deleted_cache_files"] >= 0
        assert release_data["redis_key_deleted"] is True

    async def test_url_transcription_workflow(
        self,
        api_client,
        test_data_factory,
        mock_redis,
        mock_celery,
        temp_cache_dir
    ):
        """Test URL-based transcription workflow."""
        # Mock HTTP client for URL download
        wav_data = test_data_factory.create_wav_file().getvalue()
        
        with patch('httpx.AsyncClient') as mock_httpx:
            mock_response = Mock()
            mock_response.content = wav_data
            mock_response.status_code = 200
            mock_response.headers = {"content-type": "audio/wav"}
            mock_response.raise_for_status.return_value = None
            
            mock_context = Mock()
            mock_context.__aenter__.return_value.get.return_value = mock_response
            mock_httpx.return_value = mock_context
            
            # Start transcription
            response = await api_client.transcribe_url("https://example.com/test.wav")
            assert response.status_code == 200
            
            data = response.json()
            assert_valid_task_response(data)

    async def test_s3_transcription_workflow(
        self,
        api_client,
        test_data_factory,
        mock_redis,
        mock_celery,
        mock_s3,
        temp_cache_dir,
        mock_environment
    ):
        """Test S3-based transcription workflow."""
        # Mock file operations for S3 download
        with patch('os.path.getsize', return_value=2048), \
             patch('builtins.open', create=True):
            
            response = await api_client.transcribe_s3(
                "input/audio/test.wav",
                "output/results/transcription"
            )
            assert response.status_code == 200
            
            data = response.json()
            assert_valid_task_response(data)
            
            # Verify S3 download was attempted
            mock_s3.download_file.assert_called_once()


@pytest.mark.integration
class TestErrorHandling:
    """Test error handling across the API."""

    async def test_missing_client_id_across_endpoints(self, async_client, test_data_factory):
        """Test that all endpoints properly handle missing client_id."""
        wav_file = test_data_factory.create_wav_file()
        
        # Test /transcribe
        files = {"file": ("test.wav", wav_file, "audio/wav")}
        response = await async_client.post("/transcribe", files=files)
        assert response.status_code == 400
        assert "client_id header is required" in response.json()["detail"]
        
        # Test /transcribe_url
        payload = {"url": "https://example.com/test.wav"}
        response = await async_client.post("/transcribe_url", json=payload)
        assert response.status_code == 400
        assert "client_id header is required" in response.json()["detail"]
        
        # Test /transcribe_s3
        payload = {"s3_input_path": "input/test.wav"}
        response = await async_client.post("/transcribe_s3", json=payload)
        assert response.status_code == 400
        assert "client_id header is required" in response.json()["detail"]

    async def test_invalid_file_types(self, api_client, test_data_factory):
        """Test rejection of invalid file types."""
        # Test MP3 file rejection
        mp3_data = b"fake mp3 data"
        from io import BytesIO
        
        response = await api_client.transcribe_file(
            BytesIO(mp3_data),
            "test.mp3",
            "audio/mp3"
        )
        assert response.status_code == 415
        assert "Only WAV files are accepted" in response.json()["detail"]

    async def test_s3_configuration_errors(self, api_client, test_data_factory):
        """Test S3 configuration error handling."""
        wav_file = test_data_factory.create_wav_file()
        
        # Test with missing S3 configuration
        with patch.dict(os.environ, {}, clear=True):
            response = await api_client.transcribe_file(
                wav_file,
                s3_results_path="output/results"
            )
            assert response.status_code == 501
            assert "S3 storage is not configured" in response.json()["detail"]

    async def test_invalid_s3_paths(self, api_client, test_data_factory, mock_environment):
        """Test invalid S3 path handling."""
        wav_file = test_data_factory.create_wav_file()
        
        invalid_paths = [
            "/absolute/path",
            "path/with/../dots",
            "path/ending/"
        ]
        
        for invalid_path in invalid_paths:
            response = await api_client.transcribe_file(
                wav_file,
                s3_results_path=invalid_path
            )
            assert response.status_code == 400
            assert "Invalid s3_results_path format" in response.json()["detail"]


@pytest.mark.integration
class TestServiceHealth:
    """Test service health and monitoring."""

    async def test_health_endpoint_comprehensive(self, async_client):
        """Test health endpoint with various service states."""
        response = await async_client.get("/health")
        assert response.status_code == 200
        
        data = response.json()
        assert_valid_health_response(data)

    async def test_queue_monitoring(self, async_client, mock_redis, test_data_factory):
        """Test queue status monitoring."""
        # Mock various task states
        task_keys = [b"task:1", b"task:2", b"task:3"]
        mock_redis.keys.return_value = task_keys
        
        task_metadata = {
            "task:1": test_data_factory.create_task_metadata(status="PROCESSING"),
            "task:2": test_data_factory.create_task_metadata(status="COMPLETED"),
            "task:3": test_data_factory.create_task_metadata(status="PENDING_UPLOADED")
        }
        
        def mock_get(key):
            return json.dumps(task_metadata.get(key))
        
        mock_redis.get.side_effect = mock_get
        
        response = await async_client.get("/queue")
        assert response.status_code == 200
        
        data = response.json()
        assert_valid_queue_response(data)
        assert data["active_tasks_in_queue"] == 2  # PROCESSING and PENDING_UPLOADED
        assert data["total_tracked_tasks"] == 3


@pytest.mark.integration
@pytest.mark.slow
class TestConcurrency:
    """Test concurrent request handling."""

    async def test_multiple_concurrent_uploads(
        self,
        api_client,
        test_data_factory,
        mock_redis,
        mock_celery,
        temp_cache_dir
    ):
        """Test handling multiple concurrent file uploads."""
        import asyncio
        
        # Create multiple WAV files
        files = [
            test_data_factory.create_wav_file(duration_seconds=1.0)
            for _ in range(5)
        ]
        
        # Submit all files concurrently
        tasks = [
            api_client.transcribe_file(file, f"test_{i}.wav")
            for i, file in enumerate(files)
        ]
        
        responses = await asyncio.gather(*tasks)
        
        # Verify all succeeded
        for response in responses:
            assert response.status_code == 200
            data = response.json()
            assert_valid_task_response(data)
        
        # Verify all task IDs are unique
        task_ids = [response.json()["task_id"] for response in responses]
        assert len(set(task_ids)) == len(task_ids)

    async def test_concurrent_status_checks(
        self,
        api_client,
        test_data_factory,
        mock_redis
    ):
        """Test concurrent status checks for the same task."""
        import asyncio
        
        task_id = "test-concurrent-task"
        task_metadata = test_data_factory.create_task_metadata(task_id=task_id)
        mock_redis.get.return_value = json.dumps(task_metadata)
        
        # Make multiple concurrent status requests
        tasks = [
            api_client.get_status(task_id)
            for _ in range(10)
        ]
        
        responses = await asyncio.gather(*tasks)
        
        # Verify all succeeded with same data
        for response in responses:
            assert response.status_code == 200
            data = response.json()
            assert_valid_status_response(data, task_id)


@pytest.mark.integration
@pytest.mark.redis
class TestRedisIntegration:
    """Test Redis integration scenarios."""

    async def test_redis_failure_handling(self, async_client):
        """Test API behavior when Redis is unavailable."""
        with patch('transcriber_service.app.main.redis_client', None):
            # Health check should report Redis as unavailable
            response = await async_client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert "error" in data.get("redis", "") or data.get("redis") == "not initialized"
            
            # Status endpoint should return 503
            response = await async_client.get("/status/test-task")
            assert response.status_code == 503
            
            # Queue endpoint should return 503
            response = await async_client.get("/queue")
            assert response.status_code == 503