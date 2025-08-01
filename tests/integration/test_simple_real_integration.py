"""
Simplified real integration tests that connect to localhost:8000.
These tests avoid complex fixture issues and work directly with httpx.
"""
import asyncio
import json
import time
from pathlib import Path

import httpx
import pytest


SERVICE_URL = "http://localhost:8000"
CLIENT_ID = "simple-integration-test"
AUDIO_FILE = Path("test_data/5rmAy8fgYsY_audio.wav")


@pytest.mark.asyncio
async def test_service_health():
    """Test that the service is healthy and responding."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{SERVICE_URL}/health")
        
        assert response.status_code == 200
        health_data = response.json()
        
        # Verify all expected components
        assert "fastapi" in health_data
        assert "redis" in health_data  
        assert "ollama" in health_data
        assert "celery" in health_data
        
        # FastAPI should always be ok
        assert health_data["fastapi"] == "ok"
        
        print(f"✅ Service health: {health_data}")


@pytest.mark.asyncio
async def test_queue_status():
    """Test queue status endpoint."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{SERVICE_URL}/queue")
        
        assert response.status_code == 200
        queue_data = response.json()
        
        assert "active_tasks_in_queue" in queue_data
        assert "total_tracked_tasks" in queue_data
        assert isinstance(queue_data["active_tasks_in_queue"], int)
        assert isinstance(queue_data["total_tracked_tasks"], int)
        
        print(f"✅ Queue status: {queue_data}")


@pytest.mark.asyncio
async def test_real_audio_transcription():
    """Test complete transcription workflow with real audio file."""
    if not AUDIO_FILE.exists():
        pytest.skip(f"Audio file not found: {AUDIO_FILE}")
    
    print(f"🎵 Testing with real audio file: {AUDIO_FILE} ({AUDIO_FILE.stat().st_size / 1024 / 1024:.1f}MB)")
    
    async with httpx.AsyncClient(timeout=60) as client:
        headers = {"client_id": CLIENT_ID}
        
        # Step 1: Upload file
        with open(AUDIO_FILE, "rb") as f:
            files = {"file": ("test_audio.wav", f, "audio/wav")}
            
            response = await client.post(
                f"{SERVICE_URL}/transcribe",
                files=files,
                headers=headers
            )
        
        assert response.status_code == 200, f"Upload failed: {response.text}"
        
        upload_data = response.json()
        assert "task_id" in upload_data
        task_id = upload_data["task_id"]
        
        print(f"✅ File uploaded. Task ID: {task_id}")
        
        # Step 2: Monitor progress
        max_wait = 300  # 5 minutes
        check_interval = 10  # 10 seconds
        elapsed = 0
        
        while elapsed < max_wait:
            response = await client.get(f"{SERVICE_URL}/status/{task_id}", headers=headers)
            assert response.status_code == 200
            
            status_data = response.json()
            status = status_data.get("status", "UNKNOWN")
            
            print(f"⏱️  Task status after {elapsed}s: {status}")
            
            if status == "COMPLETED":
                print("✅ Transcription completed!")
                break
            elif status == "FAILED":
                pytest.fail(f"Transcription failed: {status_data}")
            
            await asyncio.sleep(check_interval)
            elapsed += check_interval
        
        if elapsed >= max_wait:
            response = await client.get(f"{SERVICE_URL}/status/{task_id}", headers=headers)
            final_status = response.json()
            pytest.fail(f"Transcription timed out. Final status: {final_status}")
        
        # Step 3: Download results
        response = await client.get(f"{SERVICE_URL}/download/{task_id}?fmt=json", headers=headers)
        assert response.status_code == 200
        
        json_result = response.json()
        print(f"✅ JSON result preview: {str(json_result)[:200]}...")
        
        response = await client.get(f"{SERVICE_URL}/download/{task_id}?fmt=md", headers=headers)
        assert response.status_code == 200
        
        md_result = response.text
        print(f"✅ Markdown result length: {len(md_result)} chars")
        
        # Step 4: Cleanup
        response = await client.delete(f"{SERVICE_URL}/release/{task_id}", headers=headers)
        assert response.status_code == 200
        
        cleanup_data = response.json()
        print(f"✅ Cleanup completed: {cleanup_data}")


@pytest.mark.asyncio
async def test_error_handling():
    """Test error handling with invalid requests."""
    async with httpx.AsyncClient() as client:
        headers = {"client_id": CLIENT_ID}
        
        # Test non-existent task
        response = await client.get(f"{SERVICE_URL}/status/fake-task-id", headers=headers)
        assert response.status_code == 404
        
        # Test missing client_id
        response = await client.get(f"{SERVICE_URL}/status/fake-task-id")
        assert response.status_code in [400, 503]  # Either bad request or service unavailable
        
        print("✅ Error handling works correctly")


if __name__ == "__main__":
    # Allow running this file directly for quick testing
    import sys
    
    async def main():
        print("🧪 Running simple integration tests...")
        
        try:
            await test_service_health()
            await test_queue_status()
            await test_error_handling()
            
            # Only run transcription test if audio file exists
            if AUDIO_FILE.exists():
                await test_real_audio_transcription()
            else:
                print(f"⚠️  Skipping transcription test - audio file not found: {AUDIO_FILE}")
            
            print("✅ All tests passed!")
            
        except Exception as e:
            print(f"❌ Test failed: {e}")
            sys.exit(1)
    
    asyncio.run(main())