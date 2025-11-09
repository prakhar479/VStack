#!/bin/bash
# Run integration tests for V-Stack

set -e

echo "=========================================="
echo "V-Stack Integration Tests"
echo "=========================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_info() {
    echo -e "${YELLOW}ℹ${NC} $1"
}

# Check if system is running
print_info "Checking if V-Stack system is running..."
if ! docker-compose ps | grep -q "Up"; then
    print_error "V-Stack system is not running. Please start it first with:"
    echo "  ./scripts/init_system.sh"
    exit 1
fi
print_success "System is running"

# Wait for services to be ready
print_info "Waiting for services to be ready..."
sleep 5

# Run Python integration tests
print_info "Running Python integration tests..."
if python3 tests/test_integration_e2e.py; then
    print_success "Python integration tests passed"
else
    print_error "Python integration tests failed"
    exit 1
fi

# Run end-to-end workflow tests
print_info "Running end-to-end workflow tests..."
if python3 scripts/test_e2e_workflow.py; then
    print_success "End-to-end workflow tests passed"
else
    print_error "End-to-end workflow tests failed"
    exit 1
fi

# Run system monitoring check
print_info "Running system monitoring check..."
if python3 scripts/monitor_system.py; then
    print_success "System monitoring check passed"
else
    print_error "System monitoring check failed"
    exit 1
fi

echo ""
echo "=========================================="
print_success "All integration tests passed!"
echo "=========================================="
echo ""
