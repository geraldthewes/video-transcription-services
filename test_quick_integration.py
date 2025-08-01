#!/usr/bin/env python3
"""
Quick integration test to verify the transcription service works with real audio.
This bypasses pytest fixtures to avoid import issues.
"""
import asyncio
import json
import time
from pathlib import Path

import httpx

SERVICE_URL = "http://localhost:8000"
CLIENT_ID = "quick-test-client"
AUDIO_FILE = Path("test_data/5rmAy8fgYsY_audio.wav")

async def test_integration():
    """Run a complete integration test workflow."""
    print("🧪 Quick Integration Test - Video Transcription Service")
    print("=" * 60)
    
    if not AUDIO_FILE.exists():
        print(f"❌ Audio file not found: {AUDIO_FILE}")
        return False
    
    print(f"🎵 Using audio file: {AUDIO_FILE} ({AUDIO_FILE.stat().st_size / 1024 / 1024:.1f}MB)")
    
    async with httpx.AsyncClient(timeout=60) as client:
        headers = {"client_id": CLIENT_ID}
        
        # Step 1: Health check
        print("\n1️⃣ Testing service health...")
        try:
            response = await client.get(f"{SERVICE_URL}/health")
            if response.status_code == 200:
                health = response.json()
                print(f"✅ Service healthy: {health}")
            else:
                print(f"❌ Health check failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Failed to connect to service: {e}")
            return False
        
        # Step 2: Queue status
        print("\n2️⃣ Testing queue status...")
        try:
            response = await client.get(f"{SERVICE_URL}/queue")
            if response.status_code == 200:
                queue = response.json()
                print(f"✅ Queue status: {queue}")
            else:
                print(f"❌ Queue check failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Queue check error: {e}")
            return False
        
        # Step 3: Upload and transcribe
        print("\n3️⃣ Uploading audio file for transcription...")
        try:
            with open(AUDIO_FILE, "rb") as f:
                files = {"file": ("test_audio.wav", f, "audio/wav")}
                response = await client.post(
                    f"{SERVICE_URL}/transcribe",
                    files=files,
                    headers=headers
                )
            
            if response.status_code == 200:
                upload_result = response.json()
                task_id = upload_result["task_id"]
                print(f"✅ Upload successful. Task ID: {task_id}")
            else:
                print(f"❌ Upload failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"❌ Upload error: {e}")
            return False
        
        # Step 4: Monitor transcription progress
        print("\n4️⃣ Monitoring transcription progress...")
        max_wait = 300  # 5 minutes
        check_interval = 10  # 10 seconds
        elapsed = 0
        
        while elapsed < max_wait:
            try:
                response = await client.get(f"{SERVICE_URL}/status/{task_id}", headers=headers)
                if response.status_code == 200:
                    status_data = response.json()
                    status = status_data.get("status", "UNKNOWN")
                    print(f"⏱️  Status after {elapsed}s: {status}")
                    
                    if status == "COMPLETED":
                        print("✅ Transcription completed!")
                        break
                    elif status == "FAILED":
                        print(f"❌ Transcription failed: {status_data}")
                        return False
                else:
                    print(f"❌ Status check failed: {response.status_code}")
                    return False
            except Exception as e:
                print(f"❌ Status check error: {e}")
                return False
            
            await asyncio.sleep(check_interval)
            elapsed += check_interval
        
        if elapsed >= max_wait:
            print(f"❌ Transcription timed out after {max_wait}s")
            return False
        
        # Step 5: Download results
        print("\n5️⃣ Downloading transcription results...")
        try:
            # Download JSON
            response = await client.get(f"{SERVICE_URL}/download/{task_id}?fmt=json", headers=headers)
            if response.status_code == 200:
                json_result = response.json()
                print(f"✅ JSON result preview: {str(json_result)[:200]}...")
            else:
                print(f"❌ JSON download failed: {response.status_code}")
                return False
            
            # Download Markdown
            response = await client.get(f"{SERVICE_URL}/download/{task_id}?fmt=md", headers=headers)
            if response.status_code == 200:
                md_result = response.text
                print(f"✅ Markdown result length: {len(md_result)} chars")
            else:
                print(f"❌ Markdown download failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Download error: {e}")
            return False
        
        # Step 6: Cleanup
        print("\n6️⃣ Cleaning up resources...")
        try:
            response = await client.delete(f"{SERVICE_URL}/release/{task_id}", headers=headers)
            if response.status_code == 200:
                cleanup_result = response.json()
                print(f"✅ Cleanup completed: {cleanup_result}")
            else:
                print(f"❌ Cleanup failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Cleanup error: {e}")
            return False
    
    print("\n🎉 All integration tests passed successfully!")
    return True

if __name__ == "__main__":
    result = asyncio.run(test_integration())
    if not result:
        exit(1)