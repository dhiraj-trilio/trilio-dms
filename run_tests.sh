#!/bin/bash
# Test runner script for Trilio DMS

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    log_error "pytest is not installed. Install with: pip install pytest pytest-cov"
    exit 1
fi

# Parse arguments
TEST_TYPE=${1:-all}

case $TEST_TYPE in
    unit)
        log_info "Running unit tests..."
        pytest tests/ -m "not integration" -v
        ;;
    integration)
        log_info "Running integration tests..."
        if [ -z "$RUN_INTEGRATION_TESTS" ]; then
            log_warn "Integration tests require RUN_INTEGRATION_TESTS=1"
            log_warn "Also ensure RabbitMQ and MySQL are running"
        fi
        RUN_INTEGRATION_TESTS=1 pytest tests/ -m integration -v
        ;;
    all)
        log_info "Running all tests..."
        pytest tests/ -v
        ;;
    coverage)
        log_info "Running tests with coverage..."
        pytest tests/ --cov=trilio_dms --cov-report=html --cov-report=term-missing -v
        log_info "Coverage report generated in htmlcov/index.html"
        ;;
    client)
        log_info "Running client tests..."
        pytest tests/test_client.py -v
        ;;
    server)
        log_info "Running server tests..."
        pytest tests/test_server.py -v
        ;;
    *)
        log_error "Unknown test type: $TEST_TYPE"
        echo "Usage: $0 {unit|integration|all|coverage|client|server}"
        exit 1
        ;;
esac

log_info "Tests completed!"
