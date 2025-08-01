"""
Real integration tests that connect to the actual running service at localhost:8000.

These tests require:
1. Docker compose services to be running: docker compose up -d
2. Service to be healthy at http://localhost:8000
3. Real audio file: test_data/5rmAy8fgYsY_audio.wav

Run with: pytest tests/integration/test_real_service_integration.py -v
"""
import asyncio
import json
import os
import time
from pathlib import Path

import httpx
import pytest


# Configuration
SERVICE_BASE_URL = "http://localhost:8000"
TIMEOUT_SECONDS = 30
AUDIO_FILE_PATH = Path("test_data/5rmAy8fgYsY_audio.wav")
CLIENT_ID = "integration-test-client"


@pytest.fixture(scope="module")
async def real_client():
    """Create HTTP client for real service testing."""
    async with httpx.AsyncClient(
        base_url=SERVICE_BASE_URL,
        timeout=httpx.Timeout(timeout=TIMEOUT_SECONDS)
    ) as client:
        yield client


@pytest.fixture(scope="module")
async def service_health_check(real_client):
    """Verify service is running and healthy before tests."""
    try:
        response = await real_client.get("/health")
        if response.status_code != 200:
            pytest.skip(f"Service not healthy: {response.status_code}")
        
        health_data = response.json()
        if health_data.get("fastapi") != "ok":
            pytest.skip(f"FastAPI not ready: {health_data}")
            
        print(f"✅ Service health check passed: {health_data}")
        return health_data
        
    except httpx.ConnectError:
        pytest.skip("Service not running at localhost:8000. Run: docker compose up -d")
    except Exception as e:
        pytest.skip(f"Health check failed: {e}")


@pytest.fixture
def real_audio_file():
    """Load the real audio file for testing."""
    if not AUDIO_FILE_PATH.exists():
        pytest.skip(f"Audio file not found: {AUDIO_FILE_PATH}")
    
    return AUDIO_FILE_PATH


@pytest.fixture
def client_headers():
    """Standard headers for requests."""
    return {"client_id": CLIENT_ID}


class TestRealServiceIntegration:
    """Integration tests against the real running service."""

    @pytest.mark.integration
    async def test_service_health_detailed(self, real_client, service_health_check):
        """Test detailed health status of all service components."""
        response = await real_client.get("/health")
        assert response.status_code == 200
        
        health_data = response.json()
        
        # Verify all expected components are reported
        assert "fastapi" in health_data
        assert "redis" in health_data
        assert "ollama" in health_data
        assert "celery" in health_data
        
        # FastAPI should always be ok
        assert health_data["fastapi"] == "ok"
        
        print(f"Health status: {health_data}")

    @pytest.mark.integration
    async def test_queue_status(self, real_client, service_health_check):
        """Test queue status endpoint."""
        response = await real_client.get("/queue")
        assert response.status_code == 200
        
        queue_data = response.json()
        assert "active_tasks_in_queue" in queue_data
        assert "total_tracked_tasks" in queue_data
        assert isinstance(queue_data["active_tasks_in_queue"], int)
        assert isinstance(queue_data["total_tracked_tasks"], int)
        
        print(f"Queue status: {queue_data}")

    @pytest.mark.integration
    async def test_file_upload_transcription_workflow(
        self, 
        real_client, 
        service_health_check, 
        real_audio_file, 
        client_headers
    ):
        """Test complete file upload transcription workflow with real audio."""
        print(f"🎵 Testing with real audio file: {real_audio_file} ({real_audio_file.stat().st_size / 1024 / 1024:.1f}MB)")
        
        # Step 1: Upload file for transcription
        with open(real_audio_file, "rb") as f:
            files = {"file": ("test_audio.wav", f, "audio/wav")}
            
            response = await real_client.post(
                "/transcribe",
                files=files,
                headers=client_headers
            )
        
        assert response.status_code == 200, f"Upload failed: {response.text}"
        
        upload_data = response.json()
        assert "task_id" in upload_data
        task_id = upload_data["task_id"]
        
        print(f"✅ File uploaded successfully. Task ID: {task_id}")
        
        # Step 2: Monitor task progress
        max_wait_time = 300  # 5 minutes for real transcription
        check_interval = 5   # Check every 5 seconds
        elapsed_time = 0
        
        while elapsed_time < max_wait_time:
            response = await real_client.get(f"/status/{task_id}", headers=client_headers)
            assert response.status_code == 200
            
            status_data = response.json()
            status = status_data.get("status", "UNKNOWN")
            
            print(f"⏱️  Task status after {elapsed_time}s: {status}")
            
            if status == "COMPLETED":
                print("✅ Transcription completed successfully!")
                break
            elif status == "FAILED":
                pytest.fail(f"Transcription failed: {status_data}")
            elif status in ["PROCESSING", "PENDING_CELERY_DISPATCH", "PENDING_UPLOADED"]:
                # Still processing, wait and check again
                await asyncio.sleep(check_interval)
                elapsed_time += check_interval
            else:
                print(f"⚠️  Unknown status: {status}")
                await asyncio.sleep(check_interval)
                elapsed_time += check_interval
        
        if elapsed_time >= max_wait_time:
            # Get final status for debugging
            response = await real_client.get(f"/status/{task_id}", headers=client_headers)
            final_status = response.json()
            pytest.fail(f"Transcription timed out after {max_wait_time}s. Final status: {final_status}")
        
        # Step 3: Download transcription results
        # Try JSON format
        response = await real_client.get(f"/download/{task_id}?fmt=json", headers=client_headers)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")
        
        json_content = response.json()
        assert "transcript" in json_content or "segments" in json_content
        print(f"✅ JSON transcription downloaded. Content preview: {str(json_content)[:200]}...")
        
        # Try Markdown format
        response = await real_client.get(f"/download/{task_id}?fmt=md", headers=client_headers)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/markdown")
        
        md_content = response.text
        assert len(md_content) > 0
        print(f"✅ Markdown transcription downloaded. Length: {len(md_content)} chars")
        
        # Step 4: Clean up resources
        response = await real_client.delete(f"/release/{task_id}", headers=client_headers)
        assert response.status_code == 200
        
        cleanup_data = response.json()
        print(f"✅ Resources cleaned up: {cleanup_data}")

    @pytest.mark.integration
    async def test_file_upload_with_s3_results_path(
        self, 
        real_client, 
        service_health_check, 
        real_audio_file, 
        client_headers
    ):
        """Test file upload with S3 results path (will fail if S3 not configured)."""
        print(f"🎵 Testing S3 results path with real audio file")
        
        with open(real_audio_file, "rb") as f:
            files = {"file": ("test_audio.wav", f, "audio/wav")}
            data = {"s3_results_path": "integration-tests/results"}
            
            response = await real_client.post(
                "/transcribe",
                files=files,
                data=data,
                headers=client_headers
            )
        
        # This might fail with 501 if S3 is not configured, which is expected
        if response.status_code == 501:
            print("⚠️  S3 not configured (expected in test environment)")
            assert "S3 storage is not configured" in response.json()["detail"]
        elif response.status_code == 200:
            task_data = response.json()
            print(f"✅ S3 transcription started: {task_data}")
            
            # Clean up if successful
            task_id = task_data["task_id"]
            # Note: With S3 results, files won't be available for local download
            await real_client.delete(f"/release/{task_id}", headers=client_headers)
        else:
            pytest.fail(f"Unexpected response: {response.status_code} - {response.text}")

    @pytest.mark.integration
    async def test_transcribe_url_endpoint(self, real_client, service_health_check, client_headers):
        """Test URL transcription endpoint (with mock URL)."""
        # Using a small test WAV file URL (this would need to be a real accessible URL)
        payload = {
            "url": "https://www.soundjay.com/misc/sounds/beep-07.wav"  # Small test file
        }
        
        response = await real_client.post(
            "/transcribe_url",
            json=payload,
            headers=client_headers
        )
        
        # This might fail due to network issues or unsupported content type
        if response.status_code == 200:
            task_data = response.json()
            print(f"✅ URL transcription started: {task_data}")
            task_id = task_data["task_id"]
            
            # Clean up
            await asyncio.sleep(2)  # Give it a moment
            await real_client.delete(f"/release/{task_id}", headers=client_headers)
        else:
            print(f"⚠️  URL transcription failed (expected): {response.status_code} - {response.json()}")

    @pytest.mark.integration
    async def test_debug_endpoint(self, real_client, service_health_check, client_headers):
        """Test debug endpoint functionality."""
        # First create a task to debug
        with open(AUDIO_FILE_PATH, "rb") as f:
            files = {"file": ("debug_test.wav", f, "audio/wav")}
            
            response = await real_client.post(
                "/transcribe",
                files=files,
                headers=client_headers
            )
        
        if response.status_code == 200:
            task_id = response.json()["task_id"]
            
            # Test debug endpoint
            response = await real_client.get(f"/debug/task/{task_id}", headers=client_headers)
            assert response.status_code == 200
            
            debug_data = response.json()
            assert "task_id" in debug_data
            assert "metadata" in debug_data
            assert debug_data["task_id"] == task_id
            
            print(f"✅ Debug info retrieved: {debug_data}")
            
            # Clean up
            await real_client.delete(f"/release/{task_id}", headers=client_headers)

    @pytest.mark.integration
    async def test_error_handling_missing_client_id(self, real_client, service_health_check):
        """Test error handling when client_id is missing."""
        # Test various endpoints without client_id
        endpoints_to_test = [
            ("GET", "/status/fake-task-id"),
            ("GET", "/download/fake-task-id"),
            ("DELETE", "/release/fake-task-id"),
            ("GET", "/debug/task/fake-task-id")
        ]
        
        for method, endpoint in endpoints_to_test:
            if method == "GET":
                response = await real_client.get(endpoint)
            elif method == "DELETE":
                response = await real_client.delete(endpoint)
            
            # Should either require client_id (400) or fail due to missing task (404/503)
            assert response.status_code in [400, 404, 503]
            print(f"✅ {method} {endpoint}: {response.status_code}")

    @pytest.mark.integration
    async def test_invalid_task_id_handling(self, real_client, service_health_check, client_headers):
        """Test handling of invalid/non-existent task IDs."""
        fake_task_id = "non-existent-task-id"
        
        # Test status endpoint
        response = await real_client.get(f"/status/{fake_task_id}", headers=client_headers)
        assert response.status_code == 404
        assert "Task not found" in response.json()["detail"]
        
        # Test download endpoint
        response = await real_client.get(f"/download/{fake_task_id}", headers=client_headers)
        assert response.status_code == 404
        
        # Test release endpoint  
        response = await real_client.delete(f"/release/{fake_task_id}", headers=client_headers)
        assert response.status_code == 404
        
        print("✅ Invalid task ID handling works correctly")


class TestRealServicePerformance:
    """Performance and load testing against real service."""
    
    @pytest.mark.integration
    @pytest.mark.slow
    async def test_concurrent_health_checks(self, real_client, service_health_check):
        """Test service handles concurrent health check requests."""
        async def health_check():
            response = await real_client.get("/health")
            return response.status_code == 200
        
        # Run 10 concurrent health checks
        tasks = [health_check() for _ in range(10)]
        results = await asyncio.gather(*tasks)
        
        # All should succeed
        assert all(results), "Some concurrent health checks failed"
        print("✅ Concurrent health checks passed")

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_queue_status_consistency(self, real_client, service_health_check):
        """Test queue status remains consistent under load."""
        async def get_queue_status():
            response = await real_client.get("/queue")
            if response.status_code == 200:
                return response.json()
            return None
        
        # Get multiple queue status calls
        tasks = [get_queue_status() for _ in range(5)]
        results = await asyncio.gather(*tasks)
        
        valid_results = [r for r in results if r is not None]
        assert len(valid_results) > 0, "No valid queue status responses"
        
        # All should have required fields
        for result in valid_results:
            assert "active_tasks_in_queue" in result
            assert "total_tracked_tasks" in result
        
        print(f"✅ Queue status consistency check passed. Sample: {valid_results[0]}")