"""
Unit tests for the health endpoint.
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
import httpx


class TestHealthEndpoint:
    """Test suite for the /health endpoint."""

    @pytest.mark.unit
    async def test_health_check_all_services_ok(self, async_client, mock_redis):
        """Test health check when all services are healthy."""
        # Mock Redis is healthy
        mock_redis.ping.return_value = True
        
        # Mock Ollama is healthy
        with patch('httpx.AsyncClient') as mock_httpx:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_context = AsyncMock()
            mock_context.__aenter__.return_value.get.return_value = mock_response
            mock_httpx.return_value = mock_context
            
            # Mock Celery is healthy
            with patch('transcriber_service.app.main.CELERY_AVAILABLE', True), \
                 patch('transcriber_service.app.main.transcribe_audio_task') as mock_task:
                
                # Mock Celery inspect
                with patch('celery.current_app') as mock_celery_app:
                    mock_inspect = Mock()
                    mock_inspect.active.return_value = {'worker1': []}
                    mock_celery_app.control.inspect.return_value = mock_inspect
                    
                    response = await async_client.get('/health')
        
        assert response.status_code == 200
        data = response.json()
        assert data['fastapi'] == 'ok'
        assert data['redis'] == 'ok'
        assert data['ollama'] == 'ok'
        assert data['celery'] == 'ok'

    @pytest.mark.unit
    async def test_health_check_redis_connection_error(self, async_client):
        """Test health check when Redis is unavailable."""
        # Mock Redis connection error
        with patch('transcriber_service.app.main.redis_client') as mock_redis:
            mock_redis.ping.side_effect = Exception("Connection failed")
            
            # Mock Ollama is healthy
            with patch('httpx.AsyncClient') as mock_httpx:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_context = AsyncMock()
                mock_context.__aenter__.return_value.get.return_value = mock_response
                mock_httpx.return_value = mock_context
                
                response = await async_client.get('/health')
        
        assert response.status_code == 200
        data = response.json()
        assert data['fastapi'] == 'ok'
        assert 'error' in data['redis']
        assert data['ollama'] == 'ok'

    @pytest.mark.unit
    async def test_health_check_ollama_unavailable(self, async_client, mock_redis):
        """Test health check when Ollama is unavailable."""
        mock_redis.ping.return_value = True
        
        # Mock Ollama connection error
        with patch('httpx.AsyncClient') as mock_httpx:
            mock_context = AsyncMock()
            mock_context.__aenter__.side_effect = httpx.RequestError("Connection failed")
            mock_httpx.return_value = mock_context
            
            response = await async_client.get('/health')
        
        assert response.status_code == 200
        data = response.json()
        assert data['fastapi'] == 'ok'
        assert data['redis'] == 'ok'
        assert 'error' in data['ollama']

    @pytest.mark.unit
    async def test_health_check_ollama_not_configured(self, async_client, mock_redis):
        """Test health check when Ollama is not configured."""
        mock_redis.ping.return_value = True
        
        with patch('transcriber_service.app.main.OLLAMA_HOST', None):
            response = await async_client.get('/health')
        
        assert response.status_code == 200
        data = response.json()
        assert data['fastapi'] == 'ok'
        assert data['redis'] == 'ok'
        assert data['ollama'] == 'not_configured'

    @pytest.mark.unit
    async def test_health_check_celery_not_available(self, async_client, mock_redis):
        """Test health check when Celery is not available."""
        mock_redis.ping.return_value = True
        
        # Mock Ollama is healthy
        with patch('httpx.AsyncClient') as mock_httpx:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_context = AsyncMock()
            mock_context.__aenter__.return_value.get.return_value = mock_response
            mock_httpx.return_value = mock_context
            
            with patch('transcriber_service.app.main.CELERY_AVAILABLE', False):
                response = await async_client.get('/health')
        
        assert response.status_code == 200
        data = response.json()
        assert data['fastapi'] == 'ok'
        assert data['redis'] == 'ok'
        assert data['ollama'] == 'ok'
        assert data['celery'] == 'not_imported'

    @pytest.mark.unit
    async def test_health_check_celery_no_workers(self, async_client, mock_redis):
        """Test health check when Celery has no active workers."""
        mock_redis.ping.return_value = True
        
        # Mock Ollama is healthy
        with patch('httpx.AsyncClient') as mock_httpx:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_context = AsyncMock()
            mock_context.__aenter__.return_value.get.return_value = mock_response
            mock_httpx.return_value = mock_context
            
            with patch('transcriber_service.app.main.CELERY_AVAILABLE', True), \
                 patch('transcriber_service.app.main.transcribe_audio_task') as mock_task:
                
                # Mock Celery inspect with no active workers
                with patch('celery.current_app') as mock_celery_app:
                    mock_inspect = Mock()
                    mock_inspect.active.return_value = {}
                    mock_celery_app.control.inspect.return_value = mock_inspect
                    
                    response = await async_client.get('/health')
        
        assert response.status_code == 200
        data = response.json()
        assert data['fastapi'] == 'ok'
        assert data['redis'] == 'ok'
        assert data['ollama'] == 'ok'
        assert data['celery'] == 'no_workers'

    @pytest.mark.unit
    async def test_health_check_ollama_bad_status_code(self, async_client, mock_redis):
        """Test health check when Ollama returns non-2xx status code."""
        mock_redis.ping.return_value = True
        
        # Mock Ollama returns 500 error
        with patch('httpx.AsyncClient') as mock_httpx:
            mock_response = Mock()
            mock_response.status_code = 500
            mock_context = AsyncMock()
            mock_context.__aenter__.return_value.get.return_value = mock_response
            mock_httpx.return_value = mock_context
            
            response = await async_client.get('/health')
        
        assert response.status_code == 200
        data = response.json()
        assert data['fastapi'] == 'ok'
        assert data['redis'] == 'ok'
        assert data['ollama'] == 'error_code_500'