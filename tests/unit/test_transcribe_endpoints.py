"""
Unit tests for the transcription endpoints.
"""
import json
import os
import tempfile
from io import BytesIO
from unittest.mock import Mock, patch, AsyncMock

import pytest
import httpx
from fastapi import UploadFile


class TestTranscribeFileEndpoint:
    """Test suite for the /transcribe endpoint."""

    @pytest.mark.unit
    async def test_transcribe_file_success(self, async_client, mock_redis, mock_celery, temp_cache_dir, sample_wav_file):
        """Test successful file upload and transcription dispatch."""
        # Mock Redis operations
        mock_redis.set.return_value = True
        
        # Create form data with WAV file
        files = {"file": ("test.wav", sample_wav_file, "audio/wav")}
        headers = {"client_id": "test-client"}
        
        response = await async_client.post("/transcribe", files=files, headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        
        # Verify Redis was called to store metadata
        mock_redis.set.assert_called()
        
        # Verify Celery task was dispatched
        mock_celery.delay.assert_called_once()

    @pytest.mark.unit
    async def test_transcribe_file_missing_client_id(self, async_client, sample_wav_file):
        """Test transcribe file without client_id header."""
        files = {"file": ("test.wav", sample_wav_file, "audio/wav")}
        
        response = await async_client.post("/transcribe", files=files)
        
        assert response.status_code == 400
        assert "client_id header is required" in response.json()["detail"]

    @pytest.mark.unit
    async def test_transcribe_file_unsupported_content_type(self, async_client):
        """Test transcribe file with unsupported content type."""
        files = {"file": ("test.mp3", BytesIO(b"fake mp3 data"), "audio/mp3")}
        headers = {"client_id": "test-client"}
        
        response = await async_client.post("/transcribe", files=files, headers=headers)
        
        assert response.status_code == 415
        assert "Only WAV files are accepted" in response.json()["detail"]

    @pytest.mark.unit
    async def test_transcribe_file_with_s3_results_path(self, async_client, mock_redis, mock_celery, temp_cache_dir, sample_wav_file, mock_environment):
        """Test transcribe file with S3 results path."""
        mock_redis.set.return_value = True
        
        files = {"file": ("test.wav", sample_wav_file, "audio/wav")}
        data = {"s3_results_path": "client/results/output"}
        headers = {"client_id": "test-client"}
        
        response = await async_client.post("/transcribe", files=files, data=data, headers=headers)
        
        assert response.status_code == 200
        result = response.json()
        assert "task_id" in result

    @pytest.mark.unit
    async def test_transcribe_file_s3_not_configured(self, async_client, sample_wav_file):
        """Test transcribe file with S3 path but no S3 configuration."""
        files = {"file": ("test.wav", sample_wav_file, "audio/wav")}
        data = {"s3_results_path": "client/results/output"}
        headers = {"client_id": "test-client"}
        
        with patch.dict(os.environ, {}, clear=True):
            response = await async_client.post("/transcribe", files=files, data=data, headers=headers)
        
        assert response.status_code == 501
        assert "S3 storage is not configured" in response.json()["detail"]

    @pytest.mark.unit
    async def test_transcribe_file_invalid_s3_path(self, async_client, sample_wav_file, mock_environment):
        """Test transcribe file with invalid S3 path."""
        files = {"file": ("test.wav", sample_wav_file, "audio/wav")}
        data = {"s3_results_path": "/invalid/path/"}
        headers = {"client_id": "test-client"}
        
        response = await async_client.post("/transcribe", files=files, data=data, headers=headers)
        
        assert response.status_code == 400
        assert "Invalid s3_results_path format" in response.json()["detail"]


class TestTranscribeUrlEndpoint:
    """Test suite for the /transcribe_url endpoint."""

    @pytest.mark.unit
    async def test_transcribe_url_success(self, async_client, mock_redis, mock_celery, temp_cache_dir):
        """Test successful URL transcription dispatch."""
        mock_redis.set.return_value = True
        
        # Mock httpx client for URL download
        mock_wav_data = b'RIFF' + b'\x24\x08\x00\x00' + b'WAVE' + b'fmt ' + b'\x10\x00\x00\x00'
        
        with patch('httpx.AsyncClient') as mock_httpx:
            mock_response = Mock()
            mock_response.content = mock_wav_data
            mock_response.status_code = 200
            mock_response.headers = {"content-type": "audio/wav"}
            mock_response.raise_for_status.return_value = None
            
            mock_context = AsyncMock()
            mock_context.__aenter__.return_value.get.return_value = mock_response
            mock_httpx.return_value = mock_context
            
            payload = {"url": "https://example.com/test.wav"}
            headers = {"client_id": "test-client"}
            
            response = await async_client.post("/transcribe_url", json=payload, headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        
        mock_redis.set.assert_called()
        mock_celery.delay.assert_called_once()

    @pytest.mark.unit
    async def test_transcribe_url_missing_client_id(self, async_client):
        """Test transcribe URL without client_id header."""
        payload = {"url": "https://example.com/test.wav"}
        
        response = await async_client.post("/transcribe_url", json=payload)
        
        assert response.status_code == 400
        assert "client_id header is required" in response.json()["detail"]

    @pytest.mark.unit
    async def test_transcribe_url_unsupported_content_type(self, async_client, temp_cache_dir):
        """Test transcribe URL with unsupported content type."""
        with patch('httpx.AsyncClient') as mock_httpx:
            mock_response = Mock()
            mock_response.content = b"fake mp3 data"
            mock_response.status_code = 200
            mock_response.headers = {"content-type": "audio/mp3"}
            mock_response.raise_for_status.return_value = None
            
            mock_context = AsyncMock()
            mock_context.__aenter__.return_value.get.return_value = mock_response
            mock_httpx.return_value = mock_context
            
            payload = {"url": "https://example.com/test.mp3"}
            headers = {"client_id": "test-client"}
            
            response = await async_client.post("/transcribe_url", json=payload, headers=headers)
        
        assert response.status_code == 415
        assert "Only WAV audio is supported" in response.json()["detail"]

    @pytest.mark.unit
    async def test_transcribe_url_timeout(self, async_client):
        """Test transcribe URL with timeout error."""
        with patch('httpx.AsyncClient') as mock_httpx:
            mock_context = AsyncMock()
            mock_context.__aenter__.side_effect = httpx.TimeoutException("Request timeout")
            mock_httpx.return_value = mock_context
            
            payload = {"url": "https://example.com/test.wav"}
            headers = {"client_id": "test-client"}
            
            response = await async_client.post("/transcribe_url", json=payload, headers=headers)
        
        assert response.status_code == 408
        assert "Timeout downloading audio" in response.json()["detail"]

    @pytest.mark.unit
    async def test_transcribe_url_http_error(self, async_client):
        """Test transcribe URL with HTTP error."""
        with patch('httpx.AsyncClient') as mock_httpx:
            mock_response = Mock()
            mock_response.status_code = 404
            mock_response.text = "Not Found"
            
            mock_context = AsyncMock()
            mock_context.__aenter__.return_value.get.side_effect = httpx.HTTPStatusError(
                "404 Not Found", request=Mock(), response=mock_response
            )
            mock_httpx.return_value = mock_context
            
            payload = {"url": "https://example.com/missing.wav"}
            headers = {"client_id": "test-client"}
            
            response = await async_client.post("/transcribe_url", json=payload, headers=headers)
        
        assert response.status_code == 404


class TestTranscribeS3Endpoint:
    """Test suite for the /transcribe_s3 endpoint."""

    @pytest.mark.unit
    async def test_transcribe_s3_success(self, async_client, mock_redis, mock_celery, mock_s3, temp_cache_dir, mock_environment):
        """Test successful S3 transcription dispatch."""
        mock_redis.set.return_value = True
        
        # Mock file operations
        with patch('os.path.getsize', return_value=1024), \
             patch('builtins.open', create=True) as mock_open:
            
            payload = {
                "s3_input_path": "input/test.wav",
                "s3_results_path": "output/result"
            }
            headers = {"client_id": "test-client"}
            
            response = await async_client.post("/transcribe_s3", json=payload, headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        
        # Verify S3 download was called
        mock_s3.download_file.assert_called_once()
        
        # Verify Redis metadata storage
        mock_redis.set.assert_called()
        
        # Verify Celery task dispatch
        mock_celery.delay.assert_called_once()

    @pytest.mark.unit
    async def test_transcribe_s3_missing_client_id(self, async_client):
        """Test transcribe S3 without client_id header."""
        payload = {"s3_input_path": "input/test.wav"}
        
        response = await async_client.post("/transcribe_s3", json=payload)
        
        assert response.status_code == 400
        assert "client_id header is required" in response.json()["detail"]

    @pytest.mark.unit
    async def test_transcribe_s3_not_configured(self, async_client):
        """Test transcribe S3 without S3 configuration."""
        payload = {
            "s3_input_path": "input/test.wav",
            "s3_results_path": "output/result"
        }
        headers = {"client_id": "test-client"}
        
        with patch.dict(os.environ, {}, clear=True):
            response = await async_client.post("/transcribe_s3", json=payload, headers=headers)
        
        assert response.status_code == 501
        assert "S3 storage is not configured" in response.json()["detail"]

    @pytest.mark.unit
    async def test_transcribe_s3_invalid_file_extension(self, async_client, mock_s3, temp_cache_dir, mock_environment):
        """Test transcribe S3 with non-WAV file extension."""
        with patch('os.path.getsize', return_value=1024), \
             patch('builtins.open', create=True), \
             patch('os.remove') as mock_remove:
            
            payload = {"s3_input_path": "input/test.mp3"}
            headers = {"client_id": "test-client"}
            
            response = await async_client.post("/transcribe_s3", json=payload, headers=headers)
        
        assert response.status_code == 415
        assert "S3 input path must end with .wav extension" in response.json()["detail"]
        
        # Verify cleanup was attempted
        mock_remove.assert_called_once()

    @pytest.mark.unit
    async def test_transcribe_s3_file_not_found(self, async_client, mock_environment):
        """Test transcribe S3 with non-existent S3 key."""
        from botocore.exceptions import ClientError
        
        with patch('transcriber_service.app.main.create_s3_client') as mock_create:
            mock_client = Mock()
            mock_client.download_file.side_effect = ClientError(
                error_response={'Error': {'Code': 'NoSuchKey'}},
                operation_name='download_file'
            )
            mock_create.return_value = mock_client
            
            payload = {"s3_input_path": "input/missing.wav"}
            headers = {"client_id": "test-client"}
            
            response = await async_client.post("/transcribe_s3", json=payload, headers=headers)
        
        assert response.status_code == 404
        assert "not found in bucket" in response.json()["detail"]

    @pytest.mark.unit
    async def test_transcribe_s3_bucket_not_found(self, async_client, mock_environment):
        """Test transcribe S3 with non-existent bucket."""
        from botocore.exceptions import ClientError
        
        with patch('transcriber_service.app.main.create_s3_client') as mock_create:
            mock_client = Mock()
            mock_client.download_file.side_effect = ClientError(
                error_response={'Error': {'Code': 'NoSuchBucket'}},
                operation_name='download_file'
            )
            mock_create.return_value = mock_client
            
            payload = {"s3_input_path": "input/test.wav"}
            headers = {"client_id": "test-client"}
            
            response = await async_client.post("/transcribe_s3", json=payload, headers=headers)
        
        assert response.status_code == 404
        assert "bucket" in response.json()["detail"]
        assert "not found" in response.json()["detail"]