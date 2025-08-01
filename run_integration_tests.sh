#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}🧪 Video Transcription Service - Integration Test Runner${NC}"
echo "================================================================"

# Function to print colored messages
print_info() {
    echo -e "${YELLOW}ℹ️  $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${BLUE}⚠️  $1${NC}"
}

# Check if services are running
print_info "Checking if services are running..."

if ! curl -s http://localhost:8000/health > /dev/null 2>&1; then
    print_error "Service not responding at localhost:8000"
    echo ""
    echo "Please start the services first:"
    echo "  docker compose up -d"
    echo ""
    echo "Then wait for all services to be healthy:"
    echo "  curl http://localhost:8000/health"
    exit 1
fi

print_success "Service is responding at localhost:8000"

# Check service health
print_info "Checking service health..."
HEALTH_STATUS=$(curl -s http://localhost:8000/health | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(f\"FastAPI: {data.get('fastapi', 'unknown')}\")
    print(f\"Redis: {data.get('redis', 'unknown')}\")
    print(f\"Ollama: {data.get('ollama', 'unknown')}\")
    print(f\"Celery: {data.get('celery', 'unknown')}\")
    
    # Check if critical services are healthy
    if data.get('fastapi') == 'ok' and 'error' not in str(data.get('redis', '')):
        sys.exit(0)
    else:
        sys.exit(1)
except:
    print('Health check failed')
    sys.exit(1)
")

if [ $? -eq 0 ]; then
    print_success "Service health check passed"
    echo "$HEALTH_STATUS"
else
    print_warning "Some services may not be fully healthy:"
    echo "$HEALTH_STATUS"
    echo ""
    print_info "Continuing with tests anyway..."
fi

# Check for test audio file
if [ ! -f "test_data/5rmAy8fgYsY_audio.wav" ]; then
    print_error "Test audio file not found: test_data/5rmAy8fgYsY_audio.wav"
    echo "Please ensure the test audio file is available"
    exit 1
fi

AUDIO_SIZE=$(ls -lh test_data/5rmAy8fgYsY_audio.wav | awk '{print $5}')
print_success "Test audio file found: $AUDIO_SIZE"

# Parse command line arguments
VERBOSE=false
SLOW_TESTS=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --include-slow)
            SLOW_TESTS=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --verbose, -v      Verbose output"
            echo "  --include-slow     Include slow-running tests"
            echo "  --help, -h         Show this help message"
            echo ""
            echo "Prerequisites:"
            echo "  1. Start services: docker compose up -d"
            echo "  2. Ensure test audio file exists: test_data/5rmAy8fgYsY_audio.wav"
            echo ""
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Install test dependencies if needed
if ! python3 -c "import pytest" 2>/dev/null; then
    print_info "Installing test dependencies..."
    pip install -r requirements-test.txt
fi

# Build pytest command
PYTEST_CMD="python3 -m pytest tests/integration/test_real_service_integration.py --asyncio-mode=auto"

if [ "$VERBOSE" = true ]; then
    PYTEST_CMD="$PYTEST_CMD -v -s"
fi

# Add markers
MARKERS="-m integration"
if [ "$SLOW_TESTS" = false ]; then
    MARKERS="$MARKERS and not slow"
fi
PYTEST_CMD="$PYTEST_CMD $MARKERS"

print_info "Running integration tests against localhost:8000..."
print_info "Command: $PYTEST_CMD"
echo ""

# Run the tests
if eval $PYTEST_CMD; then
    print_success "All integration tests passed! 🎉"
else
    print_error "Some integration tests failed 😞"
    echo ""
    print_info "Common issues:"
    echo "  • Services not fully started (wait longer after docker compose up)"
    echo "  • GPU/Ollama not available (some features may be disabled)"
    echo "  • Network issues (URL transcription tests)"
    echo "  • S3 not configured (S3 tests will be skipped)"
    exit 1
fi

echo ""
print_success "Integration test run completed successfully!"
print_info "Tests verified:"
echo "  ✅ Service health and availability"
echo "  ✅ Real audio file transcription workflow"
echo "  ✅ Task status monitoring and progress"
echo "  ✅ Result download (JSON and Markdown)"
echo "  ✅ Resource cleanup"
echo "  ✅ Error handling and edge cases"
if [ "$SLOW_TESTS" = true ]; then
    echo "  ✅ Performance and concurrent request handling"
fi