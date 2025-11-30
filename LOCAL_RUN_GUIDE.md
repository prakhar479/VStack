# Local Execution Guide

This guide explains how to run the V-Stack system locally without Docker, using separate terminals for each service.

## Prerequisites

1.  **Python 3.11+**
2.  **Go 1.21+**
3.  **Terminal Emulator** (capable of opening multiple tabs/windows)

## 1. Setup

Run the setup script to create directories, install dependencies, and build the storage node binary.

```bash
./setup_local.sh
```

## 2. Running Services

Open **7 separate terminal tabs/windows**. In EACH terminal, first activate the virtual environment:

```bash
source venv/bin/activate
```

Then run the following commands in order:

### Terminal 1: Metadata Service
The brain of the system.

```bash
export PORT=8080
export DB_PATH=./data/metadata/metadata.db
export LOG_LEVEL=DEBUG
export HEARTBEAT_INTERVAL=10
export NODE_TIMEOUT=30
export POPULARITY_THRESHOLD=1000
export STORAGE_NODES=http://localhost:8081,http://localhost:8082,http://localhost:8083
# Disable external translation since we are already on localhost
export ENABLE_EXTERNAL_TRANSLATION=false 

python metadata-service/main.py
```

### Terminal 2: Storage Node 1
Stores the actual video chunks.

```bash
export PORT=8081
export NODE_ID=storage-node-1
export NODE_URL=http://localhost:8081
export DATA_DIR=./data/storage1
export METADATA_SERVICE_URL=http://localhost:8080
export LOG_LEVEL=DEBUG
export MAX_SUPERBLOCK_SIZE=1073741824

./storage-node/storage-node
```

### Terminal 3: Storage Node 2

```bash
export PORT=8082
export NODE_ID=storage-node-2
export NODE_URL=http://localhost:8082
export DATA_DIR=./data/storage2
export METADATA_SERVICE_URL=http://localhost:8080
export LOG_LEVEL=DEBUG
export MAX_SUPERBLOCK_SIZE=1073741824

./storage-node/storage-node
```

### Terminal 4: Storage Node 3

```bash
export PORT=8083
export NODE_ID=storage-node-3
export NODE_URL=http://localhost:8083
export DATA_DIR=./data/storage3
export METADATA_SERVICE_URL=http://localhost:8080
export LOG_LEVEL=DEBUG
export MAX_SUPERBLOCK_SIZE=1073741824

./storage-node/storage-node
```

### Terminal 5: Uploader Service
Handles video ingestion and processing.

```bash
export PORT=8084
export METADATA_SERVICE_URL=http://localhost:8080
export STORAGE_NODES=http://localhost:8081,http://localhost:8082,http://localhost:8083
export LOG_LEVEL=DEBUG
export CHUNK_SIZE=2097152
export CHUNK_DURATION=10
export MAX_CONCURRENT_UPLOADS=5
export TEMP_DIR=./data/uploads

python uploader/main.py
```

### Terminal 6: Smart Client Dashboard
Simulates a client and provides metrics.

```bash
export PORT=8086
export METADATA_SERVICE_URL=http://localhost:8080
export STORAGE_NODES=http://localhost:8081,http://localhost:8082,http://localhost:8083
export LOG_LEVEL=DEBUG
export MONITORING_INTERVAL=3
export TARGET_BUFFER_SEC=30
export LOW_WATER_MARK_SEC=15
export MAX_CONCURRENT_DOWNLOADS=4

python client/server.py
```

### Terminal 7: Demo Web Server
The main UI entry point.

```bash
export PORT=8085
export METADATA_SERVICE_URL=http://localhost:8080
export UPLOADER_SERVICE_URL=http://localhost:8084
export CLIENT_DASHBOARD_URL=http://localhost:8086

python demo/server.py
```

## 3. Accessing the System

Open your browser and go to:
**http://localhost:8085**

You should see the V-Stack Demo Dashboard.

## 4. Code Review & Architecture Analysis

This section guides you through reviewing the codebase to understand the application flow, key interfaces, and potential issues.

### System Architecture Overview

V-Stack is a distributed video storage system with the following components:

1.  **Metadata Service (Python/FastAPI):**
    *   **Role:** Coordination layer, stores video metadata, manages consensus, and handles node health.
    *   **Key File:** `metadata-service/main.py`
    *   **Database:** SQLite (via `aiosqlite`) in `metadata-service/database.py`.
    *   **Consensus:** Paxos implementation in `metadata-service/consensus.py`.

2.  **Storage Nodes (Go):**
    *   **Role:** Stores raw video chunks on disk.
    *   **Key File:** `storage-node/main.go`
    *   **Interface:** HTTP API for PUT (upload), GET (download), DELETE (cleanup).

3.  **Uploader Service (Python/FastAPI):**
    *   **Role:** Handles video uploads, splits them into chunks, and distributes them to storage nodes.
    *   **Key File:** `uploader/main.py`
    *   **Logic:** `uploader/video_processor.py` (FFmpeg wrapper) and `uploader/upload_coordinator.py`.

4.  **Smart Client (Python/Aiohttp):**
    *   **Role:** Simulates a video player that intelligently fetches chunks based on network conditions.
    *   **Key File:** `client/main.py` (Core Logic) and `client/server.py` (Dashboard API).
    *   **Logic:** `client/scheduler.py` (Adaptive scheduling) and `client/buffer_manager.py`.

5.  **Demo Server (Python/Aiohttp):**
    *   **Role:** Serves the frontend and proxies requests to backend services.
    *   **Key File:** `demo/server.py`

### Key Interfaces & API Endpoints

#### Metadata Service (`http://localhost:8080`)
*   `GET /health`: System health status.
*   `POST /video`: Create a new video record.
*   `GET /manifest/{video_id}`: Get video manifest with chunk locations.
*   `POST /chunk/{chunk_id}/commit`: Commit chunk placement (Paxos).
*   `GET /storage/overhead`: Get storage efficiency stats.

#### Storage Node (`http://localhost:8081-8083`)
*   `POST /chunk/{chunk_id}`: Upload a chunk.
*   `GET /chunk/{chunk_id}`: Download a chunk.
*   `GET /health`: Node health status.

#### Uploader Service (`http://localhost:8084`)
*   `POST /upload`: Upload a video file.
*   `GET /upload/status/{session_id}`: Check upload progress.

### Debugging & Review Steps

1.  **Trace a Request:**
    *   Start with `demo/server.py` to see how the frontend request is proxied.
    *   Follow the call to the backend service (e.g., `metadata-service`).
    *   Use `grep` to find the endpoint definition in the target service (e.g., `grep -r "@app.post" metadata-service/`).

2.  **Check Logs:**
    *   Each service logs to its terminal. Look for `INFO` for normal operations and `ERROR` for failures.
    *   Common issues: Connection refused (service not started), 404 Not Found (wrong URL/ID), 500 Internal Error (bug).

3.  **Verify Data Flow:**
    *   **Upload:** `Demo -> Uploader -> Video Processor -> Upload Coordinator -> Storage Nodes -> Metadata Service (Commit)`.
    *   **Playback:** `Client -> Metadata Service (Manifest) -> Storage Nodes (Download)`.

4.  **Identify Issues:**
    *   **Concurrency:** Check for race conditions in `metadata-service` (e.g., database access).
    *   **Network:** Ensure all services can talk to each other (check `localhost` ports).
    *   **State:** Verify `data/` directories are populated after upload.

## 5. Development Workflow

To effectively enhance V-Stack, follow this progressive workflow:

### Phase 1: Review & Knowledge Documentation
Before writing code, understand the existing system.

1.  **Read the Docs:** Start with `README.md`, `ARCHITECTURE.md`, and this guide.
2.  **Explore the Code:** Use the "Code Review" steps above to trace key flows.
3.  **Document Findings:** Create a `NOTES.md` or similar to record:
    *   Key components involved in your task.
    *   Data structures and database schemas.
    *   Potential integration points and risks.
    *   Questions or uncertainties.

### Phase 2: Planning
Define *what* you will do before doing it.

1.  **Create an Implementation Plan:** Draft a plan (e.g., `implementation_plan.md`) detailing:
    *   **Goal:** What are you trying to achieve?
    *   **Proposed Changes:** Which files will be modified and how?
    *   **Verification:** How will you test the changes?
2.  **Review the Plan:** Double-check against your knowledge documentation to ensure no conflicts.

### Phase 3: Progressive Execution
Work in small, testable increments.

1.  **Environment Setup:** Ensure your local environment is running (see Section 2).
2.  **Iterative Implementation:**
    *   **Step 1:** Implement a small piece (e.g., a new API endpoint).
    *   **Step 2:** Verify it works (e.g., `curl` the endpoint).
    *   **Step 3:** Implement the next piece (e.g., frontend integration).
    *   **Step 4:** Verify end-to-end.
3.  **Commit Often:** Save your progress frequently.

### Phase 4: Verification & Cleanup
Ensure quality and maintainability.

1.  **Run Tests:** Execute any available unit tests.
2.  **Manual Verification:** Walk through the user scenarios (Upload -> Playback).
3.  **Update Documentation:** Update `README.md` or other docs if you changed behavior.
4.  **Cleanup:** Remove temporary files or debug logs.
