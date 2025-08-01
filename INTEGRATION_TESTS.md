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

### **Quick Start**
```bash
# Run all real integration tests
./run_integration_tests.sh

# Or using Make
make test-real
```

### **With Options**
```bash
# Verbose output
./run_integration_tests.sh --verbose

# Include slow performance tests
./run_integration_tests.sh --include-slow

# Get help
./run_integration_tests.sh --help
```

### **Direct pytest**
```bash
# Run specific test file
pytest tests/integration/test_real_service_integration.py -v

# Run with markers
pytest -m "integration and not slow" tests/integration/test_real_service_integration.py -v
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
$ ./run_integration_tests.sh --verbose

🧪 Video Transcription Service - Integration Test Runner
================================================================
ℹ️  Checking if services are running...
✅ Service is responding at localhost:8000
ℹ️  Checking service health...
✅ Service health check passed
FastAPI: ok
Redis: ok
Ollama: ok
Celery: ok
✅ Test audio file found: 64M

ℹ️  Running integration tests against localhost:8000...

tests/integration/test_real_service_integration.py::TestRealServiceIntegration::test_service_health_detailed PASSED
tests/integration/test_real_service_integration.py::TestRealServiceIntegration::test_queue_status PASSED
tests/integration/test_real_service_integration.py::TestRealServiceIntegration::test_file_upload_transcription_workflow PASSED
🎵 Testing with real audio file: test_data/5rmAy8fgYsY_audio.wav (63.1MB)
✅ File uploaded successfully. Task ID: abc-123-def
⏱️  Task status after 0s: PENDING_CELERY_DISPATCH
⏱️  Task status after 5s: PROCESSING
⏱️  Task status after 45s: PROCESSING
⏱️  Task status after 120s: COMPLETED
✅ Transcription completed successfully!
✅ JSON transcription downloaded. Content preview: {"transcript": "Hello world, this is a test transcription..."
✅ Markdown transcription downloaded. Length: 2048 chars
✅ Resources cleaned up: {"deleted_cache_files": 3, "redis_key_deleted": true}

===== 8 passed in 145.23s =====
✅ All integration tests passed! 🎉
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