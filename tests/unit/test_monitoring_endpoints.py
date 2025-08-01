"""
Unit tests for monitoring endpoints (queue, debug).
"""
import json
import os
from unittest.mock import Mock, patch

import pytest


class TestQueueEndpoint:
    """Test suite for the /queue endpoint."""

    @pytest.mark.unit
    async def test_queue_status_empty(self, async_client, mock_redis):
        """Test queue status with no active tasks."""
        mock_redis.keys.return_value = []
        
        response = await async_client.get("/queue")
        
        assert response.status_code == 200
        data = response.json()
        assert data["active_tasks_in_queue"] == 0
        assert data["total_tracked_tasks"] == 0

    @pytest.mark.unit
    async def test_queue_status_with_active_tasks(self, async_client, mock_redis):
        """Test queue status with active tasks."""
        # Mock task keys
        task_keys = [b"task:123", b"task:456", b"task:789"]
        mock_redis.keys.return_value = task_keys
        
        # Mock task metadata - some active, some completed
        task_metadata = {
            "task:123": {"status": "PROCESSING", "client_id": "client1"},
            "task:456": {"status": "COMPLETED", "client_id": "client2"},
            "task:789": {"status": "PENDING_CELERY_DISPATCH", "client_id": "client3"}
        }
        
        def mock_get(key):
            return json.dumps(task_metadata.get(key))
        
        mock_redis.get.side_effect = mock_get
        
        response = await async_client.get("/queue")
        
        assert response.status_code == 200
        data = response.json()
        assert data["active_tasks_in_queue"] == 2  # PROCESSING and PENDING_CELERY_DISPATCH
        assert data["total_tracked_tasks"] == 3

    @pytest.mark.unit
    async def test_queue_status_all_active_states(self, async_client, mock_redis):
        """Test queue status with all possible active states."""
        task_keys = [b"task:1", b"task:2", b"task:3", b"task:4", b"task:5"]
        mock_redis.keys.return_value = task_keys
        
        # All different active states
        task_metadata = {
            "task:1": {"status": "PENDING_UPLOADED", "client_id": "client1"},
            "task:2": {"status": "PENDING_DOWNLOADED", "client_id": "client2"},
            "task:3": {"status": "PENDING_CELERY_DISPATCH", "client_id": "client3"},
            "task:4": {"status": "PROCESSING", "client_id": "client4"},
            "task:5": {"status": "RETRYING", "client_id": "client5"}
        }
        
        def mock_get(key):
            return json.dumps(task_metadata.get(key))
        
        mock_redis.get.side_effect = mock_get
        
        response = await async_client.get("/queue")
        
        assert response.status_code == 200
        data = response.json()
        assert data["active_tasks_in_queue"] == 5
        assert data["total_tracked_tasks"] == 5

    @pytest.mark.unit
    async def test_queue_status_redis_unavailable(self, async_client):
        """Test queue status when Redis is unavailable."""
        with patch('transcriber_service.app.main.redis_client', None):
            response = await async_client.get("/queue")
        
        assert response.status_code == 503
        assert "Redis service not available" in response.json()["detail"]

    @pytest.mark.unit
    async def test_queue_status_redis_error(self, async_client, mock_redis):
        """Test queue status when Redis throws an error."""
        import redis
        mock_redis.keys.side_effect = redis.exceptions.RedisError("Connection failed")
        
        response = await async_client.get("/queue")
        
        assert response.status_code == 500
        assert "Could not query Redis" in response.json()["detail"]

    @pytest.mark.unit
    async def test_queue_status_invalid_json(self, async_client, mock_redis):
        """Test queue status with invalid JSON in Redis."""
        task_keys = [b"task:123", b"task:456"]
        mock_redis.keys.return_value = task_keys
        
        # Return invalid JSON for one task
        def mock_get(key):
            if key == "task:123":
                return "invalid json"
            return json.dumps({"status": "PROCESSING", "client_id": "client1"})
        
        mock_redis.get.side_effect = mock_get
        
        response = await async_client.get("/queue")
        
        assert response.status_code == 200
        data = response.json()
        assert data["active_tasks_in_queue"] == 1  # Only the valid task
        assert data["total_tracked_tasks"] == 2

    @pytest.mark.unit
    async def test_queue_status_redis_get_error(self, async_client, mock_redis):
        """Test queue status when Redis get() fails for some keys."""
        import redis
        task_keys = [b"task:123", b"task:456"]
        mock_redis.keys.return_value = task_keys
        
        def mock_get(key):
            if key == "task:123":
                raise redis.exceptions.RedisError("Get failed")
            return json.dumps({"status": "PROCESSING", "client_id": "client1"})
        
        mock_redis.get.side_effect = mock_get
        
        response = await async_client.get("/queue")
        
        assert response.status_code == 200
        data = response.json()
        assert data["active_tasks_in_queue"] == 1  # Only the successful get
        assert data["total_tracked_tasks"] == 2


class TestDebugEndpoint:
    """Test suite for the /debug/task/{task_id} endpoint."""

    @pytest.mark.unit
    async def test_debug_task_success(self, async_client, mock_redis, sample_task_metadata, temp_cache_dir):
        """Test successful debug task information retrieval."""
        task_id = "test-task-123"
        sample_task_metadata["celery_task_id"] = "celery-123"
        sample_task_metadata["saved_filename"] = "test_file.wav"
        mock_redis.get.return_value = json.dumps(sample_task_metadata)
        
        # Create the file referenced in metadata
        file_path = os.path.join(temp_cache_dir, sample_task_metadata["saved_filename"])
        with open(file_path, 'w') as f:
            f.write("test content")
        
        with patch('transcriber_service.app.main.CELERY_AVAILABLE', True), \
             patch('transcriber_service.app.main.transcribe_audio_task') as mock_task:
            
            # Mock Celery result
            with patch('celery.result.AsyncResult') as mock_async_result:
                mock_result = Mock()
                mock_result.status = "SUCCESS"
                mock_result.result = "Task completed"
                mock_result.failed.return_value = False
                mock_result.traceback = None
                mock_async_result.return_value = mock_result
                
                response = await async_client.get(f"/debug/task/{task_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == task_id
        assert data["metadata"] == sample_task_metadata
        assert "celery_info" in data
        assert data["celery_info"]["celery_status"] == "SUCCESS"
        assert "file_info" in data
        assert data["file_info"]["file_exists"] is True
        assert data["file_info"]["file_size"] > 0

    @pytest.mark.unit
    async def test_debug_task_redis_unavailable(self, async_client):
        """Test debug endpoint when Redis is unavailable."""
        task_id = "test-task-123"
        
        with patch('transcriber_service.app.main.redis_client', None):
            response = await async_client.get(f"/debug/task/{task_id}")
        
        assert response.status_code == 503
        assert "Redis service not available" in response.json()["detail"]

    @pytest.mark.unit
    async def test_debug_task_not_found(self, async_client, mock_redis):
        """Test debug endpoint for non-existent task."""
        task_id = "non-existent-task"
        mock_redis.get.return_value = None
        
        response = await async_client.get(f"/debug/task/{task_id}")
        
        assert response.status_code == 404
        assert "Task not found" in response.json()["detail"]

    @pytest.mark.unit
    async def test_debug_task_no_celery(self, async_client, mock_redis, sample_task_metadata):
        """Test debug endpoint when Celery is not available."""
        task_id = "test-task-123"
        mock_redis.get.return_value = json.dumps(sample_task_metadata)
        
        with patch('transcriber_service.app.main.CELERY_AVAILABLE', False):
            response = await async_client.get(f"/debug/task/{task_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == task_id
        assert "celery_info" in data
        assert data["celery_info"] == {}  # Empty when Celery not available

    @pytest.mark.unit
    async def test_debug_task_celery_failed(self, async_client, mock_redis, sample_task_metadata):
        """Test debug endpoint for failed Celery task."""
        task_id = "test-task-123"
        sample_task_metadata["celery_task_id"] = "celery-failed-123"
        mock_redis.get.return_value = json.dumps(sample_task_metadata)
        
        with patch('transcriber_service.app.main.CELERY_AVAILABLE', True), \
             patch('transcriber_service.app.main.transcribe_audio_task'):
            
            # Mock failed Celery result
            with patch('celery.result.AsyncResult') as mock_async_result:
                mock_result = Mock()
                mock_result.status = "FAILURE"
                mock_result.result = Exception("Task failed")
                mock_result.failed.return_value = True
                mock_result.traceback = "Traceback: Error occurred"
                mock_async_result.return_value = mock_result
                
                response = await async_client.get(f"/debug/task/{task_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["celery_info"]["celery_status"] == "FAILURE"
        assert data["celery_info"]["celery_traceback"] == "Traceback: Error occurred"

    @pytest.mark.unit
    async def test_debug_task_celery_error(self, async_client, mock_redis, sample_task_metadata):
        """Test debug endpoint when Celery lookup raises an error."""
        task_id = "test-task-123"
        sample_task_metadata["celery_task_id"] = "celery-error-123"
        mock_redis.get.return_value = json.dumps(sample_task_metadata)
        
        with patch('transcriber_service.app.main.CELERY_AVAILABLE', True), \
             patch('transcriber_service.app.main.transcribe_audio_task'):
            
            # Mock Celery error
            with patch('celery.result.AsyncResult', side_effect=Exception("Celery lookup failed")):
                response = await async_client.get(f"/debug/task/{task_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert "celery_error" in data["celery_info"]
        assert "Celery lookup failed" in data["celery_info"]["celery_error"]

    @pytest.mark.unit
    async def test_debug_task_file_not_exists(self, async_client, mock_redis, sample_task_metadata, temp_cache_dir):
        """Test debug endpoint when referenced file doesn't exist."""
        task_id = "test-task-123"
        sample_task_metadata["saved_filename"] = "missing_file.wav"
        mock_redis.get.return_value = json.dumps(sample_task_metadata)
        
        response = await async_client.get(f"/debug/task/{task_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert "file_info" in data
        assert data["file_info"]["file_exists"] is False
        assert data["file_info"]["file_size"] is None

    @pytest.mark.unit
    async def test_debug_task_no_file_metadata(self, async_client, mock_redis, temp_cache_dir):
        """Test debug endpoint when task has no saved_filename."""
        task_id = "test-task-123"
        task_metadata = {
            "client_id": "test-client",
            "status": "COMPLETED",
            "task_type": "url_download"
            # No saved_filename
        }
        mock_redis.get.return_value = json.dumps(task_metadata)
        
        response = await async_client.get(f"/debug/task/{task_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["file_info"] == {}  # Empty when no saved_filename