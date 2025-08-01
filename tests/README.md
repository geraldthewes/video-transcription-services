# Test Suite Documentation

This directory contains comprehensive regression tests for the Video Transcription Service API using state-of-the-art testing frameworks.

## 🧪 Test Framework

- **pytest**: Modern Python testing framework with fixtures and parametrization
- **httpx**: Async HTTP client for FastAPI testing
- **pytest-asyncio**: Async test support
- **pytest-cov**: Code coverage reporting
- **respx**: HTTP request mocking
- **factory-boy**: Test data generation
- **freezegun**: Time/date mocking

## 📁 Directory Structure

```
tests/
├── conftest.py              # Shared fixtures and configuration
├── unit/                    # Unit tests for individual components
│   ├── test_health.py       # Health endpoint tests
│   ├── test_transcribe_endpoints.py  # Transcription endpoint tests
│   ├── test_task_management.py       # Status/download/release tests
│   └── test_monitoring_endpoints.py  # Queue/debug endpoint tests
├── integration/             # End-to-end integration tests
│   └── test_api_integration.py       # Complete workflow tests
├── utils/                   # Test utilities and helpers
│   └── test_helpers.py      # Common test utilities
└── fixtures/                # Test data and fixtures
```

## 🚀 Running Tests

### Quick Start

```bash
# Run all tests with coverage
./run_tests.sh

# Run only unit tests
./run_tests.sh --unit

# Run only integration tests
./run_tests.sh --integration

# Run tests without coverage
./run_tests.sh --no-coverage

# Verbose output
./run_tests.sh --verbose
```

### Using Make (Alternative)

```bash
# Run all tests
make test

# Run unit tests only
make test-unit

# Run integration tests only
make test-integration

# Run tests and open coverage report
make test-coverage
```

### Using pytest directly

```bash
# Install test dependencies
pip install -r requirements-test.txt

# Run all tests
pytest

# Run with coverage
pytest --cov=transcriber_service --cov-report=html

# Run specific test markers
pytest -m unit          # Unit tests only
pytest -m integration   # Integration tests only
pytest -m redis         # Redis-dependent tests
pytest -m s3            # S3-dependent tests
pytest -m slow          # Slow-running tests
```

## 🎯 Test Categories

### Unit Tests (`-m unit`)

Fast, isolated tests that mock external dependencies:

- **Health Endpoint**: Service health checks with various dependency states
- **Transcribe Endpoints**: File upload, URL, and S3 transcription initiation
- **Task Management**: Status retrieval, file downloads, resource cleanup
- **Monitoring**: Queue status and task debugging

### Integration Tests (`-m integration`)

End-to-end tests that verify complete workflows:

- **Complete Workflows**: Full transcription process from upload to download
- **Error Handling**: Comprehensive error scenario testing
- **Concurrency**: Multiple simultaneous request handling
- **Service Health**: Complete health monitoring scenarios

### Specialized Markers

- **`-m redis`**: Tests requiring Redis connectivity
- **`-m s3`**: Tests requiring S3/AWS configuration
- **`-m celery`**: Tests requiring Celery worker
- **`-m slow`**: Long-running tests (excluded by default)

## 🛠️ Test Configuration

### Environment Setup

Tests use mocked dependencies by default but can be configured for real services:

```bash
# For Redis integration tests
export REDIS_HOST=localhost
export REDIS_PORT=6379

# For S3 integration tests
export S3_STORAGE_BUCKET=test-bucket
export AWS_ACCESS_KEY_ID=test-key
export AWS_SECRET_ACCESS_KEY=test-secret
export AWS_REGION=us-east-1

# For Ollama integration tests
export OLLAMA_HOST=http://localhost:11434
```

### Coverage Configuration

Coverage is configured to:
- **Target**: `transcriber_service` package
- **Minimum**: 80% coverage required
- **Reports**: HTML, XML, and terminal output
- **Exclusions**: Test files, migrations, and configuration

## 📊 Test Data and Fixtures

### Available Fixtures

- **`async_client`**: Async HTTP test client
- **`api_client`**: High-level API test helper
- **`test_data_factory`**: Generate test data (WAV files, metadata, etc.)
- **`mock_redis`**: Mocked Redis client
- **`mock_celery`**: Mocked Celery task dispatcher
- **`mock_s3`**: Mocked S3 client
- **`temp_cache_dir`**: Temporary directory for file operations
- **`sample_task_metadata`**: Example task metadata
- **`sample_wav_file`**: Valid WAV file for testing

### Test Data Generation

```python
# Generate test WAV files
wav_file = test_data_factory.create_wav_file(duration_seconds=2.0)

# Generate task metadata
metadata = test_data_factory.create_task_metadata(
    client_id="test-client",
    status="COMPLETED"
)

# Generate transcription results
result = test_data_factory.create_transcription_result(
    text="Test transcription",
    confidence=0.95
)
```

## 🔧 Test Utilities

### API Test Client

Simplified API interaction for tests:

```python
async def test_example(api_client, test_data_factory):
    # Upload file
    wav_file = test_data_factory.create_wav_file()
    response = await api_client.transcribe_file(wav_file)
    
    # Check status
    task_id = response.json()["task_id"]
    status = await api_client.get_status(task_id)
    
    # Download results
    result = await api_client.download_result(task_id, "json")
```

### Assertion Helpers

```python
# Validate API responses
assert_valid_task_response(response.json())
assert_valid_health_response(health_data)
assert_valid_status_response(status_data, task_id)
assert_valid_queue_response(queue_data)
```

## 🐛 Debugging Tests

### Verbose Output

```bash
./run_tests.sh --verbose
# or
pytest -v -s
```

### Running Single Tests

```bash
pytest tests/unit/test_health.py::TestHealthEndpoint::test_health_check_all_services_ok -v
```

### Debug Failing Tests

```bash
pytest --pdb  # Drop into debugger on failure
pytest --lf   # Run only last failed tests
pytest --tb=short  # Shorter traceback format
```

## 📈 Coverage Reports

After running tests with coverage:

- **HTML Report**: Open `htmlcov/index.html` in browser
- **Terminal**: Coverage summary in console output
- **XML Report**: `coverage.xml` for CI/CD integration

### Coverage Targets

- **Overall**: ≥80% coverage required
- **Unit Tests**: Should achieve >90% coverage
- **Integration Tests**: Focus on workflow coverage
- **Critical Paths**: 100% coverage for security/data handling

## 🚀 Continuous Integration

The test suite is designed for CI/CD integration:

```yaml
# Example GitHub Actions snippet
- name: Run tests
  run: |
    pip install -r requirements-test.txt
    ./run_tests.sh
    
- name: Upload coverage
  uses: codecov/codecov-action@v1
  with:
    file: ./coverage.xml
```

## 🤝 Contributing

When adding new features:

1. **Add unit tests** for new functions/classes
2. **Add integration tests** for new API endpoints
3. **Update fixtures** if new test data is needed
4. **Maintain coverage** above 80%
5. **Use appropriate markers** for test categorization

### Test Naming Convention

- `test_<functionality>_<scenario>`
- `test_<endpoint>_<success|error>_<condition>`

Examples:
- `test_transcribe_file_success`
- `test_transcribe_url_timeout_error`
- `test_health_check_redis_unavailable`