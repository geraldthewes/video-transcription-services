"""
Simple working example test to demonstrate the test framework is functional.
"""
import pytest
from unittest.mock import patch, Mock


@pytest.mark.unit
async def test_health_endpoint_basic(async_client):
    """Test basic health endpoint functionality."""
    # Mock Redis to avoid connection issues
    with patch('transcriber_service.app.main.redis_client') as mock_redis_client:
        mock_redis_client.ping.return_value = True
        
        # Mock Ollama to avoid connection issues
        with patch('httpx.AsyncClient') as mock_httpx:
            mock_response = Mock()
            mock_response.status_code = 200
            
            async def mock_get(*args, **kwargs):
                return mock_response
            
            mock_httpx.return_value.__aenter__.return_value.get = mock_get
            
            # Mock Celery availability
            with patch('transcriber_service.app.main.CELERY_AVAILABLE', True), \
                 patch('transcriber_service.app.main.transcribe_audio_task') as mock_task:
                
                # Mock Celery inspect
                with patch('celery.current_app') as mock_celery_app:
                    mock_inspect = Mock()
                    mock_inspect.active.return_value = {'worker1': []}
                    mock_celery_app.control.inspect.return_value = mock_inspect
                    
                    # Make the request
                    response = await async_client.get('/health')
    
    # Verify response
    assert response.status_code == 200
    data = response.json()
    
    # Verify all required services are reported
    assert 'fastapi' in data
    assert 'redis' in data
    assert 'ollama' in data
    assert 'celery' in data
    
    # FastAPI should always be ok
    assert data['fastapi'] == 'ok'


@pytest.mark.unit
async def test_health_endpoint_redis_failure(async_client):
    """Test health endpoint when Redis fails."""
    # Mock Redis to raise an exception
    with patch('transcriber_service.app.main.redis_client') as mock_redis_client:
        mock_redis_client.ping.side_effect = Exception("Connection failed")
        
        response = await async_client.get('/health')
    
    assert response.status_code == 200
    data = response.json()
    assert data['fastapi'] == 'ok'
    assert 'error' in data['redis']


@pytest.mark.unit
async def test_missing_client_id_handling(async_client):
    """Test that endpoints properly require client_id header."""
    # Test /status endpoint
    response = await async_client.get('/status/test-task-id')
    # Should fail because redis_client is None by default
    assert response.status_code in [400, 503]  # Either bad request or service unavailable
    
    # Test with client_id header but no Redis
    headers = {"client_id": "test-client"}
    response = await async_client.get('/status/test-task-id', headers=headers)
    assert response.status_code == 503  # Service unavailable without Redis


@pytest.mark.unit
async def test_queue_endpoint_no_redis(async_client):
    """Test queue endpoint when Redis is not available."""
    # By default, redis_client is None in tests
    response = await async_client.get('/queue')
    assert response.status_code == 503
    data = response.json()
    assert "Redis service not available" in data["detail"]


@pytest.mark.unit
def test_sample_wav_file_creation(test_data_factory):
    """Test that our test data factory can create WAV files."""
    wav_file = test_data_factory.create_wav_file(duration_seconds=1.0)
    
    # Verify it's a BytesIO object
    assert hasattr(wav_file, 'read')
    assert hasattr(wav_file, 'seek')
    
    # Verify it has some content
    content = wav_file.getvalue()
    assert len(content) > 0
    
    # Verify it starts with WAV header
    wav_file.seek(0)
    header = wav_file.read(4)
    assert header == b'RIFF'


@pytest.mark.unit
def test_task_metadata_creation(test_data_factory):
    """Test that our test data factory can create task metadata."""
    metadata = test_data_factory.create_task_metadata(
        client_id="test-client",
        status="COMPLETED"
    )
    
    # Verify required fields
    assert metadata["client_id"] == "test-client"
    assert metadata["status"] == "COMPLETED"
    assert "task_type" in metadata
    assert "original_filename" in metadata
    assert "saved_filename" in metadata