#!/bin/bash
# Run all V-Stack demonstrations

echo "=========================================="
echo "V-Stack Demonstration Suite"
echo "=========================================="
echo ""

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is required but not installed."
    exit 1
fi

echo "Available demonstrations:"
echo "1. Smart vs Naive Client Comparison"
echo "2. Network Emulation Scenarios"
echo "3. Consensus Protocol Visualization (opens browser)"
echo "4. Performance Dashboard (opens browser)"
echo "5. Comprehensive Benchmarks"
echo "6. Chaos Engineering Tests"
echo "7. Run All Demos (automated)"
echo ""

read -p "Select demo (1-7) or 'q' to quit: " choice

case $choice in
    1)
        echo ""
        echo "Running Smart vs Naive Comparison..."
        python3 demo/smart_vs_naive_demo.py
        ;;
    2)
        echo ""
        echo "Running Network Emulation Scenarios..."
        python3 demo/network_emulator.py
        ;;
    3)
        echo ""
        echo "Starting Consensus Visualization Server..."
        echo "Open http://localhost:8889 in your browser"
        python3 demo/consensus_demo.py
        ;;
    4)
        echo ""
        echo "Starting Performance Dashboard..."
        echo "Open http://localhost:8888 in your browser"
        read -p "Enter video ID (or press Enter for default): " video_id
        video_id=${video_id:-test-video-001}
        python3 client/run_with_dashboard.py "$video_id"
        ;;
    5)
        echo ""
        echo "Running Comprehensive Benchmarks..."
        python3 demo/benchmark.py
        ;;
    6)
        echo ""
        echo "Running Chaos Engineering Tests..."
        python3 demo/chaos_test.py
        ;;
    7)
        echo ""
        echo "Running All Automated Demos..."
        python3 demo/run_demo.py
        ;;
    q|Q)
        echo "Exiting..."
        exit 0
        ;;
    *)
        echo "Invalid selection. Please choose 1-7 or 'q'."
        exit 1
        ;;
esac

echo ""
echo "=========================================="
echo "Demo Complete"
echo "=========================================="
