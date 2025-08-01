# 🔄 Real Integration Tests

This document describes the **real integration tests** that connect to the actual running service at `localhost:8000` and use real audio data.

## 🎯 What These Tests Do

Unlike unit tests (which are mocked), these integration tests:

✅ **Connect to real service** at `http://localhost:8000`  
✅ **Use real audio file** (`test_data/5rmAy8fgYsY_audio.wav`)  
✅ **Test complete workflows** from upload to download  
✅ **Monitor actual transcription** with real processing time  
✅ **Verify all API endpoints** work with real data  
✅ **Test error handling** with real service responses  

## 📋 Prerequisites

### 1. **Services Must Be Running**
```bash
# Start all services
docker compose up -d

# Verify services are healthy
curl http://localhost:8000/health
```

### 2. **Test Data Available**
The real audio file must be present:
```bash
ls -la test_data/5rmAy8fgYsY_audio.wav
# Should show ~66MB WAV file
```

### 3. **Test Dependencies Installed**
```bash
pip install -r requirements-test.txt
```

## 🚀 Running Integration Tests

### **Quick Start (Recommended)**
```bash
# ✅ SIMPLEST METHOD - Run direct integration test
python test_quick_integration.py

# ⚠️ Shell script method (may have pytest import issues)
./run_integration_tests.sh

# Or using Make
make test-real
```

### **Direct Python Test (Most Reliable)**
```bash
# This method always works and shows real-time progress
python test_quick_integration.py

# What it does:
# 1. ✅ Tests service health
# 2. ✅ Uploads 63MB real audio file (test_data/5rmAy8fgYsY_audio.wav)
# 3. ✅ Monitors transcription progress in real-time
# 4. ✅ Downloads JSON and Markdown results
# 5. ✅ Cleans up resources
```

### **Shell Script Options (If Working)**
```bash
# Verbose output (note: correct spelling is --verbose, not --versbose)
./run_integration_tests.sh --verbose

# Include slow performance tests
./run_integration_tests.sh --include-slow

# Get help
./run_integration_tests.sh --help
```

### **Troubleshooting Shell Script**
If `./run_integration_tests.sh` fails with pytest import errors:
```bash
# Use the direct Python method instead
python test_quick_integration.py

# The shell script has issues with conftest.py imports
# but the direct Python test bypasses these issues
```

## 🧪 Test Categories

### **Core Integration Tests**

#### ✅ **Service Health & Status**
- Detailed health check of all components
- Queue status monitoring
- Service availability verification

#### ✅ **Complete Transcription Workflow**
- Upload real audio file (66MB WAV)
- Monitor task progress in real-time
- Wait for actual transcription completion (up to 5 minutes)
- Download results in JSON and Markdown formats
- Clean up resources

#### ✅ **API Parameter Testing**
- Test new parameter names (`s3_results_path`, `s3_input_path`)
- S3 configuration handling (graceful failure if not configured)  
- Client ID validation across all endpoints

#### ✅ **Error Handling**
- Invalid task ID handling
- Missing client ID responses
- Service error conditions

### **Performance Tests** (`--include-slow`)

#### ✅ **Concurrent Request Handling**
- Multiple simultaneous health checks
- Queue status consistency under load
- Service responsiveness verification

## 📊 Expected Test Behavior

### **Successful Run Example**
```bash
$ python test_quick_integration.py

🧪 Quick Integration Test - Video Transcription Service
============================================================
🎵 Using audio file: test_data/5rmAy8fgYsY_audio.wav (63.1MB)

1️⃣ Testing service health...
✅ Service healthy: {'fastapi': 'ok', 'redis': 'ok', 'ollama': 'ok', 'celery': 'ok'}

2️⃣ Testing queue status...
✅ Queue status: {'active_tasks_in_queue': 1, 'total_tracked_tasks': 14}

3️⃣ Uploading audio file for transcription...
✅ Upload successful. Task ID: 3551a151-0383-48d1-9ac3-1cb91a26dfbb

4️⃣ Monitoring transcription progress...
⏱️  Status after 0s: PROCESSING
⏱️  Status after 10s: PROCESSING
⏱️  Status after 20s: PROCESSING
⏱️  Status after 30s: PROCESSING
⏱️  Status after 40s: PROCESSING
⏱️  Status after 50s: PROCESSING
⏱️  Status after 60s: COMPLETED
✅ Transcription completed!

5️⃣ Downloading transcription results...
✅ JSON result preview: [{"start": 0.0, "end": 4.5, "transcript": "Prior to coming to Lexington I served as the town manager..."}]
✅ Markdown result length: 8808 chars

6️⃣ Cleaning up resources...
✅ Cleanup completed: {'message': 'Task resources release processed.', 'deleted_cache_files': 3, 'files_not_found_in_cache': 0, 'redis_key_deleted': True, 'errors_deleting_files': None}

🎉 All integration tests passed successfully!
```

### **Expected Timings**
- **Health checks**: < 1 second
- **File upload**: 2-5 seconds (depends on network)
- **Transcription**: 2-5 minutes (depends on audio length & GPU)
- **Download**: < 1 second
- **Total test time**: 3-6 minutes for complete workflow

## ⚠️ Common Issues & Solutions

### **Service Not Running**
```
❌ Service not responding at localhost:8000
```
**Solution**: Start services with `docker compose up -d`

### **Partial Service Health**
```
⚠️  Some services may not be fully healthy:
FastAPI: ok
Redis: ok  
Ollama: not_configured
Celery: no_workers
```
**Impact**: Tests may still run but some features limited

### **S3 Not Configured**
```
⚠️  S3 not configured (expected in test environment)
```
**Impact**: S3-related tests will be skipped (expected behavior)

### **Transcription Timeout**
```
Transcription timed out after 300s. Final status: PROCESSING
```
**Solutions**:
- Check GPU availability: `docker compose exec worker nvidia-smi`
- Check worker logs: `docker compose logs worker`
- Increase timeout in test configuration

### **Audio File Missing**
```
❌ Test audio file not found: test_data/5rmAy8fgYsY_audio.wav
```
**Solution**: Ensure test audio file is in the correct location

## 🔧 Test Configuration

### **Timeouts & Intervals**
```python
# In test_real_service_integration.py
SERVICE_BASE_URL = "http://localhost:8000"
TIMEOUT_SECONDS = 30          # HTTP request timeout
CLIENT_ID = "integration-test-client"

# Transcription monitoring
max_wait_time = 300           # 5 minutes max wait
check_interval = 5            # Check every 5 seconds
```

### **Customization**
To modify test behavior, edit:
- `tests/integration/test_real_service_integration.py` - Main test logic
- `tests/conftest_integration.py` - Integration-specific fixtures
- `run_integration_tests.sh` - Test runner configuration

## 📈 Test Coverage

The integration tests verify:

| Component | Coverage |
|-----------|----------|
| Health endpoint | ✅ All dependency states |
| File upload | ✅ Real 66MB WAV file |
| Task monitoring | ✅ Real-time status updates |
| Transcription | ✅ Complete processing pipeline |
| Downloads | ✅ JSON & Markdown formats |
| Resource cleanup | ✅ File & metadata deletion |
| Error handling | ✅ Invalid inputs & edge cases |
| API parameters | ✅ New parameter names |
| Performance | ✅ Concurrent requests |

## 🎉 Success Criteria

A successful integration test run confirms:

1. **Service Health**: All components responding
2. **Real Data Processing**: 66MB audio file transcribed successfully  
3. **Complete Workflow**: Upload → Process → Download → Cleanup
4. **API Compatibility**: New parameter names working correctly
5. **Error Handling**: Graceful failure modes
6. **Performance**: Service handles concurrent requests

These tests provide confidence that the video transcription service works correctly with real data in a production-like environment.