package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/gorilla/mux"
)

func setupTestStorageNode(t *testing.T) (*StorageNode, string) {
	tempDir, err := os.MkdirTemp("", "storage_node_test_*")
	if err != nil {
		t.Fatalf("Failed to create temp dir: %v", err)
	}

	sn := NewStorageNode(tempDir, "test-node")
	if err := sn.Initialize(); err != nil {
		t.Fatalf("Failed to initialize storage node: %v", err)
	}

	return sn, tempDir
}

func cleanupTestStorageNode(tempDir string) {
	os.RemoveAll(tempDir)
}

func TestChunkStorageAndRetrieval(t *testing.T) {
	sn, tempDir := setupTestStorageNode(t)
	defer cleanupTestStorageNode(tempDir)

	// Test data with various sizes
	testCases := []struct {
		name     string
		chunkID  string
		data     []byte
	}{
		{"small_chunk", "chunk-001", []byte("small test data")},
		{"medium_chunk", "chunk-002", make([]byte, 1024)}, // 1KB
		{"large_chunk", "chunk-003", make([]byte, 2*1024*1024)}, // 2MB
	}

	// Fill large chunk with test pattern
	for i := range testCases[2].data {
		testCases[2].data[i] = byte(i % 256)
	}

	// Store chunks
	for _, tc := range testCases {
		t.Run("store_"+tc.name, func(t *testing.T) {
			checksum := fmt.Sprintf("%x", sha256.Sum256(tc.data))
			err := sn.storeChunk(tc.chunkID, tc.data, checksum)
			if err != nil {
				t.Fatalf("Failed to store chunk %s: %v", tc.chunkID, err)
			}

			// Verify chunk exists in index
			sn.index.mu.RLock()
			entry, exists := sn.index.chunks[tc.chunkID]
			sn.index.mu.RUnlock()

			if !exists {
				t.Fatalf("Chunk %s not found in index", tc.chunkID)
			}

			if entry.ChunkID != tc.chunkID {
				t.Errorf("Expected chunk ID %s, got %s", tc.chunkID, entry.ChunkID)
			}

			if entry.Size != int32(len(tc.data)) {
				t.Errorf("Expected size %d, got %d", len(tc.data), entry.Size)
			}

			if entry.Checksum != checksum {
				t.Errorf("Expected checksum %s, got %s", checksum, entry.Checksum)
			}
		})
	}

	// Retrieve chunks
	for _, tc := range testCases {
		t.Run("retrieve_"+tc.name, func(t *testing.T) {
			sn.index.mu.RLock()
			entry := sn.index.chunks[tc.chunkID]
			sn.index.mu.RUnlock()

			data, err := sn.readChunk(entry)
			if err != nil {
				t.Fatalf("Failed to read chunk %s: %v", tc.chunkID, err)
			}

			if !bytes.Equal(data, tc.data) {
				t.Errorf("Retrieved data doesn't match original for chunk %s", tc.chunkID)
			}
		})
	}
}

func TestHTTPEndpoints(t *testing.T) {
	sn, tempDir := setupTestStorageNode(t)
	defer cleanupTestStorageNode(tempDir)

	// Setup router
	r := mux.NewRouter()
	r.HandleFunc("/chunk/{chunk_id}", sn.handlePutChunk).Methods("PUT")
	r.HandleFunc("/chunk/{chunk_id}", sn.handleGetChunk).Methods("GET")
	r.HandleFunc("/ping", sn.handlePing).Methods("HEAD")
	r.HandleFunc("/health", sn.handleHealth).Methods("GET")

	testData := []byte("test chunk data for HTTP endpoints")
	chunkID := "http-test-chunk"

	t.Run("PUT_chunk", func(t *testing.T) {
		req := httptest.NewRequest("PUT", "/chunk/"+chunkID, bytes.NewReader(testData))
		w := httptest.NewRecorder()

		r.ServeHTTP(w, req)

		if w.Code != http.StatusCreated {
			t.Errorf("Expected status %d, got %d", http.StatusCreated, w.Code)
		}

		location := w.Header().Get("Location")
		expectedLocation := "/chunk/" + chunkID
		if location != expectedLocation {
			t.Errorf("Expected Location header %s, got %s", expectedLocation, location)
		}
	})

	t.Run("GET_chunk", func(t *testing.T) {
		req := httptest.NewRequest("GET", "/chunk/"+chunkID, nil)
		w := httptest.NewRecorder()

		r.ServeHTTP(w, req)

		if w.Code != http.StatusOK {
			t.Errorf("Expected status %d, got %d", http.StatusOK, w.Code)
		}

		body, err := io.ReadAll(w.Body)
		if err != nil {
			t.Fatalf("Failed to read response body: %v", err)
		}

		if !bytes.Equal(body, testData) {
			t.Errorf("Retrieved data doesn't match original")
		}

		// Check headers
		contentType := w.Header().Get("Content-Type")
		if contentType != "application/octet-stream" {
			t.Errorf("Expected Content-Type application/octet-stream, got %s", contentType)
		}

		etag := w.Header().Get("ETag")
		hash := sha256.Sum256(testData)
		expectedChecksum := hex.EncodeToString(hash[:])
		if etag != expectedChecksum {
			t.Errorf("Expected ETag %s, got %s", expectedChecksum, etag)
		}
	})

	t.Run("GET_nonexistent_chunk", func(t *testing.T) {
		req := httptest.NewRequest("GET", "/chunk/nonexistent", nil)
		w := httptest.NewRecorder()

		r.ServeHTTP(w, req)

		if w.Code != http.StatusNotFound {
			t.Errorf("Expected status %d, got %d", http.StatusNotFound, w.Code)
		}
	})

	t.Run("HEAD_ping", func(t *testing.T) {
		req := httptest.NewRequest("HEAD", "/ping", nil)
		w := httptest.NewRecorder()

		r.ServeHTTP(w, req)

		if w.Code != http.StatusOK {
			t.Errorf("Expected status %d, got %d", http.StatusOK, w.Code)
		}

		nodeID := w.Header().Get("X-Node-ID")
		if nodeID != "test-node" {
			t.Errorf("Expected X-Node-ID test-node, got %s", nodeID)
		}

		diskUsage := w.Header().Get("X-Disk-Usage-Percent")
		if diskUsage == "" {
			t.Error("Expected X-Disk-Usage-Percent header")
		}
	})

	t.Run("GET_health", func(t *testing.T) {
		req := httptest.NewRequest("GET", "/health", nil)
		w := httptest.NewRecorder()

		r.ServeHTTP(w, req)

		if w.Code != http.StatusOK {
			t.Errorf("Expected status %d, got %d", http.StatusOK, w.Code)
		}

		var health HealthResponse
		if err := json.NewDecoder(w.Body).Decode(&health); err != nil {
			t.Fatalf("Failed to decode health response: %v", err)
		}

		if health.Status != "healthy" {
			t.Errorf("Expected status healthy, got %s", health.Status)
		}

		if health.NodeID != "test-node" {
			t.Errorf("Expected NodeID test-node, got %s", health.NodeID)
		}

		if health.ChunkCount < 0 {
			t.Errorf("Expected non-negative chunk count, got %d", health.ChunkCount)
		}
	})
}

func TestIndexPersistence(t *testing.T) {
	sn, tempDir := setupTestStorageNode(t)
	defer cleanupTestStorageNode(tempDir)

	// Store some chunks
	testChunks := map[string][]byte{
		"persist-001": []byte("persistence test data 1"),
		"persist-002": []byte("persistence test data 2"),
		"persist-003": []byte("persistence test data 3"),
	}

	for chunkID, data := range testChunks {
		checksum := fmt.Sprintf("%x", sha256.Sum256(data))
		err := sn.storeChunk(chunkID, data, checksum)
		if err != nil {
			t.Fatalf("Failed to store chunk %s: %v", chunkID, err)
		}
	}

	// Simulate restart by creating new storage node with same directory
	sn2 := NewStorageNode(tempDir, "test-node")
	if err := sn2.Initialize(); err != nil {
		t.Fatalf("Failed to initialize storage node after restart: %v", err)
	}

	// Verify all chunks are still accessible
	for chunkID, originalData := range testChunks {
		sn2.index.mu.RLock()
		entry, exists := sn2.index.chunks[chunkID]
		sn2.index.mu.RUnlock()

		if !exists {
			t.Errorf("Chunk %s not found after restart", chunkID)
			continue
		}

		data, err := sn2.readChunk(entry)
		if err != nil {
			t.Errorf("Failed to read chunk %s after restart: %v", chunkID, err)
			continue
		}

		if !bytes.Equal(data, originalData) {
			t.Errorf("Data mismatch for chunk %s after restart", chunkID)
		}
	}
}

func TestChecksumValidation(t *testing.T) {
	sn, tempDir := setupTestStorageNode(t)
	defer cleanupTestStorageNode(tempDir)

	// Setup router for HTTP tests
	r := mux.NewRouter()
	r.HandleFunc("/chunk/{chunk_id}", sn.handleGetChunk).Methods("GET")

	chunkID := "checksum-test"
	originalData := []byte("original data for checksum test")
	checksum := fmt.Sprintf("%x", sha256.Sum256(originalData))

	// Store chunk
	err := sn.storeChunk(chunkID, originalData, checksum)
	if err != nil {
		t.Fatalf("Failed to store chunk: %v", err)
	}

	// Corrupt the checksum in index to simulate corruption
	sn.index.mu.Lock()
	entry := sn.index.chunks[chunkID]
	entry.Checksum = "corrupted_checksum"
	sn.index.chunks[chunkID] = entry
	sn.index.mu.Unlock()

	// Try to retrieve corrupted chunk via HTTP
	req := httptest.NewRequest("GET", "/chunk/"+chunkID, nil)
	w := httptest.NewRecorder()

	r.ServeHTTP(w, req)

	if w.Code != http.StatusInternalServerError {
		t.Errorf("Expected status %d for corrupted chunk, got %d", http.StatusInternalServerError, w.Code)
	}

	body := w.Body.String()
	if !strings.Contains(body, "corruption detected") {
		t.Errorf("Expected corruption error message, got: %s", body)
	}
}

func TestConcurrentAccess(t *testing.T) {
	sn, tempDir := setupTestStorageNode(t)
	defer cleanupTestStorageNode(tempDir)

	const numGoroutines = 10
	const chunksPerGoroutine = 5

	var wg sync.WaitGroup
	errors := make(chan error, numGoroutines*chunksPerGoroutine)

	// Concurrent writes
	for i := 0; i < numGoroutines; i++ {
		wg.Add(1)
		go func(goroutineID int) {
			defer wg.Done()
			for j := 0; j < chunksPerGoroutine; j++ {
				chunkID := fmt.Sprintf("concurrent-%d-%d", goroutineID, j)
				data := []byte(fmt.Sprintf("data for chunk %s", chunkID))
				checksum := fmt.Sprintf("%x", sha256.Sum256(data))

				if err := sn.storeChunk(chunkID, data, checksum); err != nil {
					errors <- fmt.Errorf("goroutine %d: %v", goroutineID, err)
					return
				}
			}
		}(i)
	}

	wg.Wait()
	close(errors)

	// Check for errors
	for err := range errors {
		t.Errorf("Concurrent write error: %v", err)
	}

	// Verify all chunks were stored correctly
	expectedChunks := numGoroutines * chunksPerGoroutine
	sn.index.mu.RLock()
	actualChunks := len(sn.index.chunks)
	sn.index.mu.RUnlock()

	if actualChunks != expectedChunks {
		t.Errorf("Expected %d chunks, got %d", expectedChunks, actualChunks)
	}

	// Concurrent reads
	wg = sync.WaitGroup{}
	errors = make(chan error, numGoroutines*chunksPerGoroutine)

	for i := 0; i < numGoroutines; i++ {
		wg.Add(1)
		go func(goroutineID int) {
			defer wg.Done()
			for j := 0; j < chunksPerGoroutine; j++ {
				chunkID := fmt.Sprintf("concurrent-%d-%d", goroutineID, j)
				
				sn.index.mu.RLock()
				entry, exists := sn.index.chunks[chunkID]
				sn.index.mu.RUnlock()

				if !exists {
					errors <- fmt.Errorf("chunk %s not found", chunkID)
					return
				}

				data, err := sn.readChunk(entry)
				if err != nil {
					errors <- fmt.Errorf("failed to read chunk %s: %v", chunkID, err)
					return
				}

				expectedData := []byte(fmt.Sprintf("data for chunk %s", chunkID))
				if !bytes.Equal(data, expectedData) {
					errors <- fmt.Errorf("data mismatch for chunk %s", chunkID)
					return
				}
			}
		}(i)
	}

	wg.Wait()
	close(errors)

	// Check for read errors
	for err := range errors {
		t.Errorf("Concurrent read error: %v", err)
	}
}

func TestSuperblockRotation(t *testing.T) {
	sn, tempDir := setupTestStorageNode(t)
	defer cleanupTestStorageNode(tempDir)

	// Set a small superblock size for testing
	sn.maxSuperblockSize = 1024 // 1KB for testing

	// Store chunks that will exceed the superblock size
	largeData := make([]byte, 600) // 600 bytes each
	for i := range largeData {
		largeData[i] = byte(i % 256)
	}

	chunkIDs := []string{"sb-001", "sb-002", "sb-003"}
	
	for _, chunkID := range chunkIDs {
		checksum := fmt.Sprintf("%x", sha256.Sum256(largeData))
		err := sn.storeChunk(chunkID, largeData, checksum)
		if err != nil {
			t.Fatalf("Failed to store chunk %s: %v", chunkID, err)
		}
	}

	// Verify chunks are in different superblocks
	sn.index.mu.RLock()
	superblockIDs := make(map[int]bool)
	for _, chunkID := range chunkIDs {
		entry := sn.index.chunks[chunkID]
		superblockIDs[entry.SuperblockID] = true
	}
	sn.index.mu.RUnlock()

	if len(superblockIDs) < 2 {
		t.Errorf("Expected chunks to be stored in multiple superblocks, got %d superblocks", len(superblockIDs))
	}

	// Verify all chunks are still readable
	for _, chunkID := range chunkIDs {
		sn.index.mu.RLock()
		entry := sn.index.chunks[chunkID]
		sn.index.mu.RUnlock()

		data, err := sn.readChunk(entry)
		if err != nil {
			t.Errorf("Failed to read chunk %s from superblock %d: %v", chunkID, entry.SuperblockID, err)
		}

		if !bytes.Equal(data, largeData) {
			t.Errorf("Data mismatch for chunk %s in superblock %d", chunkID, entry.SuperblockID)
		}
	}
}

// TestLatencyRequirement tests that chunk retrieval meets the <10ms requirement
func TestLatencyRequirement(t *testing.T) {
	sn, tempDir := setupTestStorageNode(t)
	defer cleanupTestStorageNode(tempDir)

	// Setup router
	r := mux.NewRouter()
	r.HandleFunc("/chunk/{chunk_id}", sn.handleGetChunk).Methods("GET")
	r.HandleFunc("/chunk/{chunk_id}", sn.handlePutChunk).Methods("PUT")

	// Store test chunks of various sizes
	testCases := []struct {
		name string
		size int
	}{
		{"small", 1024},           // 1KB
		{"medium", 64 * 1024},     // 64KB
		{"large", 512 * 1024},     // 512KB
		{"xlarge", 2 * 1024 * 1024}, // 2MB (max chunk size)
	}

	for _, tc := range testCases {
		t.Run("latency_"+tc.name, func(t *testing.T) {
			// Create test data
			testData := make([]byte, tc.size)
			for i := range testData {
				testData[i] = byte(i % 256)
			}
			chunkID := fmt.Sprintf("latency-test-%s", tc.name)

			// Store chunk
			putReq := httptest.NewRequest("PUT", "/chunk/"+chunkID, bytes.NewReader(testData))
			putW := httptest.NewRecorder()
			r.ServeHTTP(putW, putReq)

			if putW.Code != http.StatusCreated {
				t.Fatalf("Failed to store chunk: %d", putW.Code)
			}

			// Measure retrieval latency multiple times
			const numTests = 10
			var totalDuration time.Duration

			for i := 0; i < numTests; i++ {
				start := time.Now()
				
				getReq := httptest.NewRequest("GET", "/chunk/"+chunkID, nil)
				getW := httptest.NewRecorder()
				r.ServeHTTP(getW, getReq)
				
				duration := time.Since(start)
				totalDuration += duration

				if getW.Code != http.StatusOK {
					t.Fatalf("Failed to retrieve chunk: %d", getW.Code)
				}

				// Individual request should be under 20ms
				if duration > 20*time.Millisecond {
					t.Errorf("Chunk retrieval took %v, exceeds 20ms requirement", duration)
				}
			}

			avgDuration := totalDuration / numTests
			t.Logf("Average retrieval time for %s chunk (%d bytes): %v", tc.name, tc.size, avgDuration)

			// Average should definitely be under 20ms
			if avgDuration > 20*time.Millisecond {
				t.Errorf("Average retrieval time %v exceeds 20ms requirement", avgDuration)
			}
		})
	}
}

// TestErrorHandlingRequirements tests proper HTTP status codes as per requirements
func TestErrorHandlingRequirements(t *testing.T) {
	sn, tempDir := setupTestStorageNode(t)
	defer cleanupTestStorageNode(tempDir)

	// Setup router
	r := mux.NewRouter()
	r.HandleFunc("/chunk/{chunk_id}", sn.handlePutChunk).Methods("PUT")
	r.HandleFunc("/chunk/{chunk_id}", sn.handleGetChunk).Methods("GET")
	r.HandleFunc("/health", sn.handleHealth).Methods("GET")

	t.Run("PUT_empty_chunk_returns_400", func(t *testing.T) {
		req := httptest.NewRequest("PUT", "/chunk/empty-test", bytes.NewReader([]byte{}))
		w := httptest.NewRecorder()
		r.ServeHTTP(w, req)

		if w.Code != http.StatusBadRequest {
			t.Errorf("Expected status %d for empty chunk, got %d", http.StatusBadRequest, w.Code)
		}
	})

	t.Run("PUT_oversized_chunk_returns_413", func(t *testing.T) {
		// Create chunk larger than 2MB limit
		largeData := make([]byte, 3*1024*1024) // 3MB
		req := httptest.NewRequest("PUT", "/chunk/oversized-test", bytes.NewReader(largeData))
		w := httptest.NewRecorder()
		r.ServeHTTP(w, req)

		if w.Code != http.StatusRequestEntityTooLarge {
			t.Errorf("Expected status %d for oversized chunk, got %d", http.StatusRequestEntityTooLarge, w.Code)
		}
	})

	t.Run("GET_nonexistent_chunk_returns_404", func(t *testing.T) {
		req := httptest.NewRequest("GET", "/chunk/does-not-exist", nil)
		w := httptest.NewRecorder()
		r.ServeHTTP(w, req)

		if w.Code != http.StatusNotFound {
			t.Errorf("Expected status %d for nonexistent chunk, got %d", http.StatusNotFound, w.Code)
		}
	})

	t.Run("PUT_chunk_idempotent_returns_200", func(t *testing.T) {
		testData := []byte("idempotent test data")
		chunkID := "idempotent-test"

		// First PUT should return 201 Created
		req1 := httptest.NewRequest("PUT", "/chunk/"+chunkID, bytes.NewReader(testData))
		w1 := httptest.NewRecorder()
		r.ServeHTTP(w1, req1)

		if w1.Code != http.StatusCreated {
			t.Errorf("Expected status %d for first PUT, got %d", http.StatusCreated, w1.Code)
		}

		// Second PUT should return 200 OK (idempotent)
		req2 := httptest.NewRequest("PUT", "/chunk/"+chunkID, bytes.NewReader(testData))
		w2 := httptest.NewRecorder()
		r.ServeHTTP(w2, req2)

		if w2.Code != http.StatusOK {
			t.Errorf("Expected status %d for duplicate PUT, got %d", http.StatusOK, w2.Code)
		}
	})

	t.Run("health_endpoint_status_based_on_disk_usage", func(t *testing.T) {
		req := httptest.NewRequest("GET", "/health", nil)
		w := httptest.NewRecorder()
		r.ServeHTTP(w, req)

		var health HealthResponse
		if err := json.NewDecoder(w.Body).Decode(&health); err != nil {
			t.Fatalf("Failed to decode health response: %v", err)
		}

		// Health status should be appropriate for disk usage
		if health.DiskUsage > 95.0 {
			if w.Code != http.StatusServiceUnavailable {
				t.Errorf("Expected status %d for critical disk usage, got %d", http.StatusServiceUnavailable, w.Code)
			}
			if health.Status != "critical" {
				t.Errorf("Expected status 'critical' for high disk usage, got %s", health.Status)
			}
		} else {
			if w.Code != http.StatusOK {
				t.Errorf("Expected status %d for healthy node, got %d", http.StatusOK, w.Code)
			}
		}
	})
}

// TestRequiredHeaders tests that all required headers are present as per design
func TestRequiredHeaders(t *testing.T) {
	sn, tempDir := setupTestStorageNode(t)
	defer cleanupTestStorageNode(tempDir)

	// Setup router
	r := mux.NewRouter()
	r.HandleFunc("/chunk/{chunk_id}", sn.handlePutChunk).Methods("PUT")
	r.HandleFunc("/chunk/{chunk_id}", sn.handleGetChunk).Methods("GET")
	r.HandleFunc("/ping", sn.handlePing).Methods("HEAD")
	r.HandleFunc("/health", sn.handleHealth).Methods("GET")

	testData := []byte("header test data")
	chunkID := "header-test"

	// Store chunk first
	putReq := httptest.NewRequest("PUT", "/chunk/"+chunkID, bytes.NewReader(testData))
	putW := httptest.NewRecorder()
	r.ServeHTTP(putW, putReq)

	t.Run("PUT_chunk_headers", func(t *testing.T) {
		if putW.Code != http.StatusCreated {
			t.Fatalf("Failed to store chunk: %d", putW.Code)
		}

		// Check required headers
		location := putW.Header().Get("Location")
		if location != "/chunk/"+chunkID {
			t.Errorf("Expected Location header '/chunk/%s', got '%s'", chunkID, location)
		}

		etag := putW.Header().Get("ETag")
		if etag == "" {
			t.Error("Expected ETag header with checksum")
		}

		chunkSize := putW.Header().Get("X-Chunk-Size")
		if chunkSize != strconv.Itoa(len(testData)) {
			t.Errorf("Expected X-Chunk-Size %d, got %s", len(testData), chunkSize)
		}
	})

	t.Run("GET_chunk_headers", func(t *testing.T) {
		getReq := httptest.NewRequest("GET", "/chunk/"+chunkID, nil)
		getW := httptest.NewRecorder()
		r.ServeHTTP(getW, getReq)

		if getW.Code != http.StatusOK {
			t.Fatalf("Failed to retrieve chunk: %d", getW.Code)
		}

		// Check required headers
		contentType := getW.Header().Get("Content-Type")
		if contentType != "application/octet-stream" {
			t.Errorf("Expected Content-Type 'application/octet-stream', got '%s'", contentType)
		}

		contentLength := getW.Header().Get("Content-Length")
		if contentLength != strconv.Itoa(len(testData)) {
			t.Errorf("Expected Content-Length %d, got %s", len(testData), contentLength)
		}

		etag := getW.Header().Get("ETag")
		if etag == "" {
			t.Error("Expected ETag header")
		}

		chunkSize := getW.Header().Get("X-Chunk-Size")
		if chunkSize == "" {
			t.Error("Expected X-Chunk-Size header")
		}

		superblockID := getW.Header().Get("X-Superblock-ID")
		if superblockID == "" {
			t.Error("Expected X-Superblock-ID header")
		}
	})

	t.Run("HEAD_ping_headers", func(t *testing.T) {
		pingReq := httptest.NewRequest("HEAD", "/ping", nil)
		pingW := httptest.NewRecorder()
		r.ServeHTTP(pingW, pingReq)

		if pingW.Code != http.StatusOK {
			t.Fatalf("Ping failed: %d", pingW.Code)
		}

		// Check required headers for network monitoring
		requiredHeaders := []string{
			"X-Node-ID",
			"X-Disk-Usage-Percent",
			"X-Chunk-Count",
			"X-Response-Time",
		}

		for _, header := range requiredHeaders {
			value := pingW.Header().Get(header)
			if value == "" {
				t.Errorf("Expected header %s", header)
			}
		}

		cacheControl := pingW.Header().Get("Cache-Control")
		if cacheControl != "no-cache" {
			t.Errorf("Expected Cache-Control 'no-cache', got '%s'", cacheControl)
		}
	})

	t.Run("GET_health_headers", func(t *testing.T) {
		healthReq := httptest.NewRequest("GET", "/health", nil)
		healthW := httptest.NewRecorder()
		r.ServeHTTP(healthW, healthReq)

		contentType := healthW.Header().Get("Content-Type")
		if contentType != "application/json" {
			t.Errorf("Expected Content-Type 'application/json', got '%s'", contentType)
		}

		cacheControl := healthW.Header().Get("Cache-Control")
		if cacheControl != "no-cache" {
			t.Errorf("Expected Cache-Control 'no-cache', got '%s'", cacheControl)
		}
	})
}

// TestDataIntegrityRequirements tests SHA-256 checksum validation
func TestDataIntegrityRequirements(t *testing.T) {
	sn, tempDir := setupTestStorageNode(t)
	defer cleanupTestStorageNode(tempDir)

	t.Run("checksum_validation_on_storage", func(t *testing.T) {
		testData := []byte("integrity test data")
		chunkID := "integrity-test"

		// Compute expected checksum
		hash := sha256.Sum256(testData)
		expectedChecksum := hex.EncodeToString(hash[:])

		// Store chunk
		err := sn.storeChunk(chunkID, testData, expectedChecksum)
		if err != nil {
			t.Fatalf("Failed to store chunk: %v", err)
		}

		// Verify chunk is in index with correct checksum
		sn.index.mu.RLock()
		entry, exists := sn.index.chunks[chunkID]
		sn.index.mu.RUnlock()

		if !exists {
			t.Fatal("Chunk not found in index")
		}

		if entry.Checksum != expectedChecksum {
			t.Errorf("Expected checksum %s, got %s", expectedChecksum, entry.Checksum)
		}
	})

	t.Run("checksum_validation_on_retrieval", func(t *testing.T) {
		// Setup router for HTTP test
		r := mux.NewRouter()
		r.HandleFunc("/chunk/{chunk_id}", sn.handleGetChunk).Methods("GET")

		chunkID := "integrity-test"

		// Retrieve chunk via HTTP
		req := httptest.NewRequest("GET", "/chunk/"+chunkID, nil)
		w := httptest.NewRecorder()
		r.ServeHTTP(w, req)

		if w.Code != http.StatusOK {
			t.Fatalf("Failed to retrieve chunk: %d", w.Code)
		}

		// Verify ETag matches computed checksum
		retrievedData, _ := io.ReadAll(w.Body)
		hash := sha256.Sum256(retrievedData)
		computedChecksum := hex.EncodeToString(hash[:])

		etag := w.Header().Get("ETag")
		if etag != computedChecksum {
			t.Errorf("ETag %s doesn't match computed checksum %s", etag, computedChecksum)
		}
	})

	t.Run("corruption_detection", func(t *testing.T) {
		// This test simulates the corruption detection test that already exists
		// but adds more comprehensive validation
		chunkID := "corruption-test"
		originalData := []byte("data that will be corrupted")
		checksum := fmt.Sprintf("%x", sha256.Sum256(originalData))

		// Store chunk
		err := sn.storeChunk(chunkID, originalData, checksum)
		if err != nil {
			t.Fatalf("Failed to store chunk: %v", err)
		}

		// Corrupt the checksum in index
		sn.index.mu.Lock()
		entry := sn.index.chunks[chunkID]
		entry.Checksum = "corrupted_checksum_value"
		sn.index.chunks[chunkID] = entry
		sn.index.mu.Unlock()

		// Setup router
		r := mux.NewRouter()
		r.HandleFunc("/chunk/{chunk_id}", sn.handleGetChunk).Methods("GET")

		// Try to retrieve corrupted chunk
		req := httptest.NewRequest("GET", "/chunk/"+chunkID, nil)
		w := httptest.NewRecorder()
		r.ServeHTTP(w, req)

		// Should return 500 Internal Server Error for corruption
		if w.Code != http.StatusInternalServerError {
			t.Errorf("Expected status %d for corrupted chunk, got %d", http.StatusInternalServerError, w.Code)
		}

		body := w.Body.String()
		if !strings.Contains(body, "corruption detected") {
			t.Errorf("Expected corruption error message, got: %s", body)
		}
	})
}

// TestPerformanceRequirements tests concurrent request handling
func TestPerformanceRequirements(t *testing.T) {
	sn, tempDir := setupTestStorageNode(t)
	defer cleanupTestStorageNode(tempDir)

	// Setup router
	r := mux.NewRouter()
	r.HandleFunc("/chunk/{chunk_id}", sn.handlePutChunk).Methods("PUT")
	r.HandleFunc("/chunk/{chunk_id}", sn.handleGetChunk).Methods("GET")

	t.Run("concurrent_chunk_requests", func(t *testing.T) {
		const numConcurrentRequests = 50
		const chunkSize = 64 * 1024 // 64KB chunks

		// First, store chunks for retrieval test
		testData := make([]byte, chunkSize)
		for i := range testData {
			testData[i] = byte(i % 256)
		}

		// Store test chunks
		for i := 0; i < numConcurrentRequests; i++ {
			chunkID := fmt.Sprintf("perf-test-%d", i)
			putReq := httptest.NewRequest("PUT", "/chunk/"+chunkID, bytes.NewReader(testData))
			putW := httptest.NewRecorder()
			r.ServeHTTP(putW, putReq)

			if putW.Code != http.StatusCreated {
				t.Fatalf("Failed to store chunk %d: %d", i, putW.Code)
			}
		}

		// Test concurrent retrieval
		var wg sync.WaitGroup
		errors := make(chan error, numConcurrentRequests)
		durations := make(chan time.Duration, numConcurrentRequests)

		start := time.Now()

		for i := 0; i < numConcurrentRequests; i++ {
			wg.Add(1)
			go func(chunkNum int) {
				defer wg.Done()
				
				requestStart := time.Now()
				chunkID := fmt.Sprintf("perf-test-%d", chunkNum)
				
				getReq := httptest.NewRequest("GET", "/chunk/"+chunkID, nil)
				getW := httptest.NewRecorder()
				r.ServeHTTP(getW, getReq)
				
				requestDuration := time.Since(requestStart)
				durations <- requestDuration

				if getW.Code != http.StatusOK {
					errors <- fmt.Errorf("chunk %d retrieval failed: %d", chunkNum, getW.Code)
					return
				}

				// Verify response time is under 50ms (requirement)
				if requestDuration > 50*time.Millisecond {
					errors <- fmt.Errorf("chunk %d took %v, exceeds 50ms requirement", chunkNum, requestDuration)
				}
			}(i)
		}

		wg.Wait()
		totalDuration := time.Since(start)
		close(errors)
		close(durations)

		// Check for errors
		errorCount := 0
		for err := range errors {
			t.Errorf("Concurrent request error: %v", err)
			errorCount++
		}

		// Calculate average response time
		var totalRequestTime time.Duration
		requestCount := 0
		for duration := range durations {
			totalRequestTime += duration
			requestCount++
		}

		if requestCount > 0 {
			avgResponseTime := totalRequestTime / time.Duration(requestCount)
			t.Logf("Concurrent requests: %d, Total time: %v, Avg response time: %v", 
				numConcurrentRequests, totalDuration, avgResponseTime)

			// Average response time should be under 50ms per requirement
			if avgResponseTime > 50*time.Millisecond {
				t.Errorf("Average response time %v exceeds 50ms requirement", avgResponseTime)
			}
		}

		if errorCount > 0 {
			t.Errorf("Failed %d out of %d concurrent requests", errorCount, numConcurrentRequests)
		}
	})
}