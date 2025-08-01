#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🧪 Video Transcription Service - Test Runner${NC}"
echo "=================================================="

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

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is not installed or not in PATH"
    exit 1
fi

# Install test dependencies if requirements-test.txt exists
if [ -f "requirements-test.txt" ]; then
    print_info "Installing test dependencies..."
    pip install -r requirements-test.txt
    print_success "Test dependencies installed"
else
    print_error "requirements-test.txt not found"
    exit 1
fi

# Parse command line arguments
TEST_TYPE="all"
COVERAGE=true
VERBOSE=false
MARKERS=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --unit)
            TEST_TYPE="unit"
            MARKERS="-m unit"
            shift
            ;;
        --integration)
            TEST_TYPE="integration"
            MARKERS="-m integration"
            shift
            ;;
        --no-coverage)
            COVERAGE=false
            shift
            ;;
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --unit           Run only unit tests"
            echo "  --integration    Run only integration tests"
            echo "  --no-coverage    Skip coverage reporting"
            echo "  --verbose, -v    Verbose output"
            echo "  --help, -h       Show this help message"
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Build pytest command
PYTEST_CMD="python -m pytest --asyncio-mode=auto"

if [ "$VERBOSE" = true ]; then
    PYTEST_CMD="$PYTEST_CMD -v"
fi

if [ "$COVERAGE" = true ]; then
    PYTEST_CMD="$PYTEST_CMD --cov=transcriber_service --cov-report=html:htmlcov --cov-report=term-missing --cov-report=xml"
fi

if [ -n "$MARKERS" ]; then
    PYTEST_CMD="$PYTEST_CMD $MARKERS"
fi

# Add test directory
PYTEST_CMD="$PYTEST_CMD tests/"

print_info "Running $TEST_TYPE tests..."
print_info "Command: $PYTEST_CMD"
echo ""

# Run the tests
if eval $PYTEST_CMD; then
    print_success "All tests passed! 🎉"
    
    if [ "$COVERAGE" = true ]; then
        echo ""
        print_info "Coverage report generated:"
        echo "  📄 HTML: htmlcov/index.html"
        echo "  📄 XML:  coverage.xml"
    fi
else
    print_error "Some tests failed 😞"
    exit 1
fi

echo ""
print_success "Test run completed successfully!"