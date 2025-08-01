"""
Unit tests for task management endpoints (status, download, release).
"""
import json
import os
import tempfile
from unittest.mock import Mock, patch

import pytest


class TestTaskStatusEndpoint:
    """Test suite for the /status/{task_id} endpoint."""

    @pytest.mark.unit
    async def test_get_task_status_success(self, async_client, mock_redis, sample_task_metadata):
        """Test successful task status retrieval."""
        task_id = "test-task-123"
        mock_redis.get.return_value = json.dumps(sample_task_metadata)
        
        headers = {"client_id": "test-client"}
        response = await async_client.get(f"/status/{task_id}", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == task_id
        assert data["status"] == sample_task_metadata["status"]
        assert data["details"] == sample_task_metadata

    @pytest.mark.unit
    async def test_get_task_status_redis_unavailable(self, async_client):
        """Test task status when Redis is unavailable."""
        task_id = "test-task-123"
        
        with patch('transcriber_service.app.main.redis_client', None):
            response = await async_client.get(f"/status/{task_id}")
        
        assert response.status_code == 503
        assert "Redis service not available" in response.json()["detail"]

    @pytest.mark.unit
    async def test_get_task_status_not_found(self, async_client, mock_redis):
        """Test task status for non-existent task."""
        task_id = "non-existent-task"
        mock_redis.get.return_value = None
        
        response = await async_client.get(f"/status/{task_id}")
        
        assert response.status_code == 404
        assert "Task not found" in response.json()["detail"]

    @pytest.mark.unit
    async def test_get_task_status_wrong_client(self, async_client, mock_redis, sample_task_metadata):
        """Test task status with wrong client_id."""
        task_id = "test-task-123"
        sample_task_metadata["client_id"] = "other-client"
        mock_redis.get.return_value = json.dumps(sample_task_metadata)
        
        headers = {"client_id": "test-client"}
        response = await async_client.get(f"/status/{task_id}", headers=headers)
        
        assert response.status_code == 403
        assert "Access denied" in response.json()["detail"]

    @pytest.mark.unit
    async def test_get_task_status_no_client_id_check(self, async_client, mock_redis, sample_task_metadata):
        """Test task status without client_id header (should work for any client)."""
        task_id = "test-task-123"
        mock_redis.get.return_value = json.dumps(sample_task_metadata)
        
        response = await async_client.get(f"/status/{task_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == task_id


class TestDownloadEndpoint:
    """Test suite for the /download/{task_id} endpoint."""

    @pytest.mark.unit
    async def test_download_json_success(self, async_client, mock_redis, sample_task_metadata, temp_cache_dir):
        """Test successful JSON file download."""
        task_id = "test-task-123"
        sample_task_metadata["status"] = "COMPLETED"
        sample_task_metadata["s3_results_path"] = None  # Local download
        mock_redis.get.return_value = json.dumps(sample_task_metadata)
        
        # Create test file
        test_content = {"transcript": "test content"}
        file_path = os.path.join(temp_cache_dir, sample_task_metadata["transcribed_json_file"])
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w') as f:
            json.dump(test_content, f)
        
        headers = {"client_id": "test-client"}
        response = await async_client.get(f"/download/{task_id}?fmt=json", headers=headers)
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json; charset=utf-8"

    @pytest.mark.unit
    async def test_download_markdown_success(self, async_client, mock_redis, sample_task_metadata, temp_cache_dir):
        """Test successful Markdown file download."""
        task_id = "test-task-123"
        sample_task_metadata["status"] = "COMPLETED"
        sample_task_metadata["s3_results_path"] = None
        mock_redis.get.return_value = json.dumps(sample_task_metadata)
        
        # Create test file
        test_content = "# Test Transcript\n\nThis is a test."
        file_path = os.path.join(temp_cache_dir, sample_task_metadata["transcribed_md_file"])
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w') as f:
            f.write(test_content)
        
        headers = {"client_id": "test-client"}
        response = await async_client.get(f"/download/{task_id}?fmt=md", headers=headers)
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/markdown; charset=utf-8"

    @pytest.mark.unit
    async def test_download_redis_unavailable(self, async_client):
        """Test download when Redis is unavailable."""
        task_id = "test-task-123"
        
        with patch('transcriber_service.app.main.redis_client', None):
            response = await async_client.get(f"/download/{task_id}")
        
        assert response.status_code == 503
        assert "Redis service not available" in response.json()["detail"]

    @pytest.mark.unit
    async def test_download_invalid_format(self, async_client, mock_redis, sample_task_metadata):
        """Test download with invalid format parameter."""
        task_id = "test-task-123"
        mock_redis.get.return_value = json.dumps(sample_task_metadata)
        
        response = await async_client.get(f"/download/{task_id}?fmt=invalid")
        
        assert response.status_code == 400
        assert "Invalid format" in response.json()["detail"]

    @pytest.mark.unit
    async def test_download_task_not_found(self, async_client, mock_redis):
        """Test download for non-existent task."""
        task_id = "non-existent-task"
        mock_redis.get.return_value = None
        
        response = await async_client.get(f"/download/{task_id}")
        
        assert response.status_code == 404
        assert "Task not found" in response.json()["detail"]

    @pytest.mark.unit
    async def test_download_wrong_client(self, async_client, mock_redis, sample_task_metadata):
        """Test download with wrong client_id."""
        task_id = "test-task-123"
        sample_task_metadata["client_id"] = "other-client"
        mock_redis.get.return_value = json.dumps(sample_task_metadata)
        
        headers = {"client_id": "test-client"}
        response = await async_client.get(f"/download/{task_id}", headers=headers)
        
        assert response.status_code == 403
        assert "Access denied" in response.json()["detail"]

    @pytest.mark.unit
    async def test_download_s3_task_blocked(self, async_client, mock_redis, sample_task_metadata):
        """Test download blocked for S3 tasks."""
        task_id = "test-task-123"
        sample_task_metadata["s3_results_path"] = "output/results"
        mock_redis.get.return_value = json.dumps(sample_task_metadata)
        
        headers = {"client_id": "test-client"}
        response = await async_client.get(f"/download/{task_id}", headers=headers)
        
        assert response.status_code == 400
        assert "s3_results_path must be downloaded directly from S3" in response.json()["detail"]

    @pytest.mark.unit
    async def test_download_task_not_completed(self, async_client, mock_redis, sample_task_metadata):
        """Test download for non-completed task."""
        task_id = "test-task-123"
        sample_task_metadata["status"] = "PROCESSING"
        sample_task_metadata["s3_results_path"] = None
        mock_redis.get.return_value = json.dumps(sample_task_metadata)
        
        headers = {"client_id": "test-client"}
        response = await async_client.get(f"/download/{task_id}", headers=headers)
        
        assert response.status_code == 400
        assert "Download is only available for COMPLETED tasks" in response.json()["detail"]

    @pytest.mark.unit
    async def test_download_file_not_found(self, async_client, mock_redis, sample_task_metadata, temp_cache_dir):
        """Test download when file doesn't exist on disk."""
        task_id = "test-task-123"
        sample_task_metadata["status"] = "COMPLETED"
        sample_task_metadata["s3_results_path"] = None
        mock_redis.get.return_value = json.dumps(sample_task_metadata)
        
        headers = {"client_id": "test-client"}
        response = await async_client.get(f"/download/{task_id}?fmt=json", headers=headers)
        
        assert response.status_code == 404
        assert "not found on server" in response.json()["detail"]


class TestReleaseEndpoint:
    """Test suite for the /release/{task_id} endpoint."""

    @pytest.mark.unit
    async def test_release_task_success(self, async_client, mock_redis, sample_task_metadata, temp_cache_dir):
        """Test successful task resource release."""
        task_id = "test-task-123"
        sample_task_metadata["s3_results_path"] = None  # Local files
        mock_redis.get.return_value = json.dumps(sample_task_metadata)
        mock_redis.delete.return_value = True
        
        # Create test files to be deleted
        files_to_create = [
            sample_task_metadata["saved_filename"],
            sample_task_metadata["transcribed_json_file"],
            sample_task_metadata["transcribed_md_file"]
        ]
        
        for filename in files_to_create:
            file_path = os.path.join(temp_cache_dir, filename)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'w') as f:
                f.write("test content")
        
        headers = {"client_id": "test-client"}
        response = await async_client.delete(f"/release/{task_id}", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["deleted_cache_files"] == 3
        assert data["redis_key_deleted"] is True
        assert data["errors_deleting_files"] is None

    @pytest.mark.unit
    async def test_release_task_redis_unavailable(self, async_client):
        """Test release when Redis is unavailable."""
        task_id = "test-task-123"
        
        with patch('transcriber_service.app.main.redis_client', None):
            response = await async_client.delete(f"/release/{task_id}")
        
        assert response.status_code == 503
        assert "Redis service not available" in response.json()["detail"]

    @pytest.mark.unit
    async def test_release_task_not_found(self, async_client, mock_redis):
        """Test release for non-existent task."""
        task_id = "non-existent-task"
        mock_redis.get.return_value = None
        
        response = await async_client.delete(f"/release/{task_id}")
        
        assert response.status_code == 404
        assert "Task not found" in response.json()["detail"]

    @pytest.mark.unit
    async def test_release_wrong_client(self, async_client, mock_redis, sample_task_metadata):
        """Test release with wrong client_id."""
        task_id = "test-task-123"
        sample_task_metadata["client_id"] = "other-client"
        mock_redis.get.return_value = json.dumps(sample_task_metadata)
        
        headers = {"client_id": "test-client"}
        response = await async_client.delete(f"/release/{task_id}", headers=headers)
        
        assert response.status_code == 403
        assert "Access denied" in response.json()["detail"]

    @pytest.mark.unit
    async def test_release_s3_task(self, async_client, mock_redis, sample_task_metadata):
        """Test release for S3 task (should not delete original audio file)."""
        task_id = "test-task-123"
        sample_task_metadata["s3_results_path"] = "output/results"
        mock_redis.get.return_value = json.dumps(sample_task_metadata)
        mock_redis.delete.return_value = True
        
        headers = {"client_id": "test-client"}
        response = await async_client.delete(f"/release/{task_id}", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        # Should only delete transcribed files, not the original saved file
        assert data["redis_key_deleted"] is True

    @pytest.mark.unit
    async def test_release_with_file_errors(self, async_client, mock_redis, sample_task_metadata, temp_cache_dir):
        """Test release when some files can't be deleted."""
        task_id = "test-task-123"
        sample_task_metadata["s3_results_path"] = None
        mock_redis.get.return_value = json.dumps(sample_task_metadata)
        
        # Create one file but make it read-only to simulate deletion error
        file_path = os.path.join(temp_cache_dir, sample_task_metadata["saved_filename"])
        with open(file_path, 'w') as f:
            f.write("test content")
        
        # Mock os.remove to raise an error for one file
        original_remove = os.remove
        def mock_remove(path):
            if sample_task_metadata["saved_filename"] in path:
                raise OSError("Permission denied")
            return original_remove(path)
        
        with patch('os.remove', side_effect=mock_remove):
            headers = {"client_id": "test-client"}
            response = await async_client.delete(f"/release/{task_id}", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["redis_key_deleted"] is False  # Redis key not deleted due to file errors
        assert data["errors_deleting_files"] is not None
        assert len(data["errors_deleting_files"]) > 0