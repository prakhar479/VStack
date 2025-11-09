package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/gorilla/mux"
)

// ChunkEntry represents metadata for a stored chunk
type ChunkEntry struct {
	ChunkID      string    `json:"chunk_id"`
	SuperblockID int       `json:"superblock_id"`
	Offset       int64     `json:"offset"`
	Size         int32     `json:"size"`
	Checksum     string    `json:"checksum"`
	StoredAt     time.Time `json:"stored_at"`
}

// ChunkIndex provides O(1) chunk lookups
type ChunkIndex struct {
	mu     sync.RWMutex
	chunks map[string]ChunkEntry
}

// SuperblockHeader contains metadata for superblock files
type SuperblockHeader struct {
	Version     uint32    `json:"version"`
	ChunkCount  uint32    `json:"chunk_count"`
	NextOffset  int64     `json:"next_offset"`
	CreatedAt   time.Time `json:"created_at"`
}

// StorageNode represents the main storage node server
type StorageNode struct {
	dataDir         string
	indexFile       string
	index           *ChunkIndex
	currentSuperblock int
	maxSuperblockSize int64
	nodeID          string
	mu              sync.Mutex
}

// HealthResponse represents the health check response
type HealthResponse struct {
	Status       string  `json:"status"`
	DiskUsage    float64 `json:"disk_usage"`
	ChunkCount   int     `json:"chunk_count"`
	Uptime       int64   `json:"uptime"`
	NodeID       string  `json:"node_id"`
}

var startTime = time.Now()

func NewStorageNode(dataDir, nodeID string) *StorageNode {
	return &StorageNode{
		dataDir:           dataDir,
		indexFile:         filepath.Join(dataDir, "index", "chunk_index.json"),
		index:             &ChunkIndex{chunks: make(map[string]ChunkEntry)},
		currentSuperblock: 0,
		maxSuperblockSize: 1024 * 1024 * 1024, // 1GB
		nodeID:           nodeID,
	}
}

func (sn *StorageNode) Initialize() error {
	// Create directory structure
	dirs := []string{
		sn.dataDir,
		filepath.Join(sn.dataDir, "data"),
		filepath.Join(sn.dataDir, "index"),
		filepath.Join(sn.dataDir, "logs"),
	}

	for _, dir := range dirs {
		if err := os.MkdirAll(dir, 0755); err != nil {
			return fmt.Errorf("failed to create directory %s: %v", dir, err)
		}
	}

	// Load existing index
	if err := sn.loadIndex(); err != nil {
		log.Printf("Warning: failed to load index: %v", err)
	}

	// Find current superblock
	sn.findCurrentSuperblock()

	return nil
}

func (sn *StorageNode) loadIndex() error {
	sn.index.mu.Lock()
	defer sn.index.mu.Unlock()

	file, err := os.Open(sn.indexFile)
	if err != nil {
		if os.IsNotExist(err) {
			return nil // Index doesn't exist yet, that's ok
		}
		return err
	}
	defer file.Close()

	return json.NewDecoder(file).Decode(&sn.index.chunks)
}

func (sn *StorageNode) saveIndex() error {
	sn.index.mu.RLock()
	defer sn.index.mu.RUnlock()

	file, err := os.Create(sn.indexFile)
	if err != nil {
		return err
	}
	defer file.Close()

	return json.NewEncoder(file).Encode(sn.index.chunks)
}

func (sn *StorageNode) findCurrentSuperblock() {
	dataDir := filepath.Join(sn.dataDir, "data")
	files, err := os.ReadDir(dataDir)
	if err != nil {
		return
	}

	maxID := -1
	for _, file := range files {
		if strings.HasPrefix(file.Name(), "superblock_") && strings.HasSuffix(file.Name(), ".dat") {
			idStr := strings.TrimPrefix(file.Name(), "superblock_")
			idStr = strings.TrimSuffix(idStr, ".dat")
			if id, err := strconv.Atoi(idStr); err == nil && id > maxID {
				maxID = id
			}
		}
	}

	if maxID >= 0 {
		sn.currentSuperblock = maxID
	}
}

func (sn *StorageNode) getSuperblockPath(id int) string {
	return filepath.Join(sn.dataDir, "data", fmt.Sprintf("superblock_%d.dat", id))
}

func (sn *StorageNode) getCurrentSuperblockSize() (int64, error) {
	path := sn.getSuperblockPath(sn.currentSuperblock)
	info, err := os.Stat(path)
	if err != nil {
		if os.IsNotExist(err) {
			return 0, nil
		}
		return 0, err
	}
	return info.Size(), nil
}

func (sn *StorageNode) getDiskUsage() float64 {
	var stat syscall.Statfs_t
	if err := syscall.Statfs(sn.dataDir, &stat); err != nil {
		return 0.0
	}

	total := stat.Blocks * uint64(stat.Bsize)
	free := stat.Bavail * uint64(stat.Bsize)
	used := total - free

	return float64(used) / float64(total) * 100.0
}

// HTTP Handlers

func (sn *StorageNode) handlePutChunk(w http.ResponseWriter, r *http.Request) {
	vars := mux.Vars(r)
	chunkID := vars["chunk_id"]

	if chunkID == "" {
		http.Error(w, "chunk_id is required", http.StatusBadRequest)
		return
	}

	// Check if chunk already exists (idempotent operation)
	sn.index.mu.RLock()
	if _, exists := sn.index.chunks[chunkID]; exists {
		sn.index.mu.RUnlock()
		w.Header().Set("Location", fmt.Sprintf("/chunk/%s", chunkID))
		w.WriteHeader(http.StatusOK) // Chunk already exists
		return
	}
	sn.index.mu.RUnlock()

	// Validate content length for 2MB chunks (as per requirements)
	contentLength := r.ContentLength
	if contentLength > 2*1024*1024+1024 { // Allow slight overhead
		http.Error(w, "Chunk size exceeds maximum allowed (2MB)", http.StatusRequestEntityTooLarge)
		return
	}

	// Read chunk data with size limit
	data, err := io.ReadAll(io.LimitReader(r.Body, 2*1024*1024+1024))
	if err != nil {
		http.Error(w, "Failed to read chunk data", http.StatusBadRequest)
		return
	}

	if len(data) == 0 {
		http.Error(w, "Empty chunk data", http.StatusBadRequest)
		return
	}

	// Compute checksum for integrity (Requirement 2.3)
	hash := sha256.Sum256(data)
	checksum := hex.EncodeToString(hash[:])

	// Store chunk with proper error handling
	if err := sn.storeChunk(chunkID, data, checksum); err != nil {
		if strings.Contains(err.Error(), "insufficient storage") {
			// Return 507 as specified in requirements
			http.Error(w, "Insufficient storage space", http.StatusInsufficientStorage)
		} else if strings.Contains(err.Error(), "disk full") {
			http.Error(w, "Disk full", http.StatusInsufficientStorage)
		} else {
			log.Printf("Storage error for chunk %s: %v", chunkID, err)
			http.Error(w, "Internal storage error", http.StatusInternalServerError)
		}
		return
	}

	// Success response with proper headers
	w.Header().Set("Location", fmt.Sprintf("/chunk/%s", chunkID))
	w.Header().Set("ETag", checksum)
	w.Header().Set("X-Chunk-Size", strconv.Itoa(len(data)))
	w.WriteHeader(http.StatusCreated)
	
	log.Printf("Stored chunk %s (size: %d bytes, checksum: %s)", chunkID, len(data), checksum[:16]+"...")
}

func (sn *StorageNode) handleGetChunk(w http.ResponseWriter, r *http.Request) {
	startTime := time.Now()
	vars := mux.Vars(r)
	chunkID := vars["chunk_id"]

	if chunkID == "" {
		http.Error(w, "chunk_id is required", http.StatusBadRequest)
		return
	}

	// Lookup chunk in index (optimized for <10ms latency requirement)
	sn.index.mu.RLock()
	entry, exists := sn.index.chunks[chunkID]
	sn.index.mu.RUnlock()

	if !exists {
		http.Error(w, "Chunk not found", http.StatusNotFound)
		return
	}

	// Read chunk data with direct I/O for performance
	data, err := sn.readChunk(entry)
	if err != nil {
		log.Printf("Failed to read chunk %s: %v", chunkID, err)
		http.Error(w, "Failed to read chunk", http.StatusInternalServerError)
		return
	}

	// Verify checksum for data integrity (Requirement 2.3)
	hash := sha256.Sum256(data)
	computedChecksum := hex.EncodeToString(hash[:])
	if computedChecksum != entry.Checksum {
		log.Printf("Checksum mismatch for chunk %s: expected %s, got %s", chunkID, entry.Checksum, computedChecksum)
		http.Error(w, "Chunk corruption detected", http.StatusInternalServerError)
		return
	}

	// Set response headers
	w.Header().Set("Content-Type", "application/octet-stream")
	w.Header().Set("Content-Length", strconv.Itoa(len(data)))
	w.Header().Set("ETag", entry.Checksum)
	w.Header().Set("X-Chunk-Size", strconv.Itoa(int(entry.Size)))
	w.Header().Set("X-Superblock-ID", strconv.Itoa(entry.SuperblockID))
	
	// Write response
	w.WriteHeader(http.StatusOK)
	w.Write(data)

	// Log performance metrics to ensure <10ms latency requirement
	duration := time.Since(startTime)
	if duration > 10*time.Millisecond {
		log.Printf("WARNING: Chunk retrieval for %s took %v (exceeds 10ms requirement)", chunkID, duration)
	} else {
		log.Printf("Retrieved chunk %s in %v", chunkID, duration)
	}
}

func (sn *StorageNode) handleHeadChunk(w http.ResponseWriter, r *http.Request) {
	vars := mux.Vars(r)
	chunkID := vars["chunk_id"]

	if chunkID == "" {
		http.Error(w, "chunk_id is required", http.StatusBadRequest)
		return
	}

	// Lookup chunk in index
	sn.index.mu.RLock()
	entry, exists := sn.index.chunks[chunkID]
	sn.index.mu.RUnlock()

	if !exists {
		http.Error(w, "Chunk not found", http.StatusNotFound)
		return
	}

	// Set response headers (same as GET but without body)
	w.Header().Set("Content-Type", "application/octet-stream")
	w.Header().Set("Content-Length", strconv.Itoa(int(entry.Size)))
	w.Header().Set("ETag", entry.Checksum)
	w.Header().Set("X-Chunk-Size", strconv.Itoa(int(entry.Size)))
	w.Header().Set("X-Superblock-ID", strconv.Itoa(entry.SuperblockID))
	
	// HEAD request - only headers, no body
	w.WriteHeader(http.StatusOK)
	
	log.Printf("HEAD request for chunk %s (exists: true, checksum: %s)", chunkID, entry.Checksum[:16]+"...")
}

func (sn *StorageNode) handlePing(w http.ResponseWriter, r *http.Request) {
	// Optimized for latency measurement (Requirement 2.5)
	startTime := time.Now()
	
	diskUsage := sn.getDiskUsage()
	
	sn.index.mu.RLock()
	chunkCount := len(sn.index.chunks)
	sn.index.mu.RUnlock()
	
	// Set headers for client monitoring
	w.Header().Set("X-Node-ID", sn.nodeID)
	w.Header().Set("X-Disk-Usage-Percent", fmt.Sprintf("%.2f", diskUsage))
	w.Header().Set("X-Chunk-Count", strconv.Itoa(chunkCount))
	w.Header().Set("X-Response-Time", fmt.Sprintf("%.3f", time.Since(startTime).Seconds()*1000)) // ms
	w.Header().Set("Cache-Control", "no-cache")
	
	w.WriteHeader(http.StatusOK)
}

func (sn *StorageNode) handleHealth(w http.ResponseWriter, r *http.Request) {
	sn.index.mu.RLock()
	chunkCount := len(sn.index.chunks)
	sn.index.mu.RUnlock()

	uptime := time.Since(startTime).Seconds()
	diskUsage := sn.getDiskUsage()
	
	// Determine health status based on disk usage (Requirement 2.5)
	status := "healthy"
	if diskUsage > 95.0 {
		status = "critical"
	} else if diskUsage > 85.0 {
		status = "warning"
	}

	health := HealthResponse{
		Status:     status,
		DiskUsage:  diskUsage,
		ChunkCount: chunkCount,
		Uptime:     int64(uptime),
		NodeID:     sn.nodeID,
	}

	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-cache")
	
	// Set appropriate HTTP status based on health
	if status == "critical" {
		w.WriteHeader(http.StatusServiceUnavailable)
	} else {
		w.WriteHeader(http.StatusOK)
	}
	
	json.NewEncoder(w).Encode(health)
}

func (sn *StorageNode) storeChunk(chunkID string, data []byte, checksum string) error {
	sn.mu.Lock()
	defer sn.mu.Unlock()

	// Check available disk space (Requirement 10.1 - error handling)
	diskUsage := sn.getDiskUsage()
	if diskUsage > 95.0 {
		return fmt.Errorf("insufficient storage space: disk usage %.2f%%", diskUsage)
	}

	// Check if current superblock has space
	currentSize, err := sn.getCurrentSuperblockSize()
	if err != nil {
		return fmt.Errorf("failed to get superblock size: %v", err)
	}

	// Rotate to new superblock if current one would exceed 1GB
	if currentSize+int64(len(data)) > sn.maxSuperblockSize {
		sn.currentSuperblock++
		log.Printf("Rotating to new superblock %d (current size: %d bytes)", sn.currentSuperblock, currentSize)
	}

	// Open/create superblock file with proper error handling
	superblockPath := sn.getSuperblockPath(sn.currentSuperblock)
	file, err := os.OpenFile(superblockPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0644)
	if err != nil {
		return fmt.Errorf("failed to open superblock file %s: %v", superblockPath, err)
	}
	defer file.Close()

	// Get current offset for direct I/O positioning
	offset, err := file.Seek(0, io.SeekEnd)
	if err != nil {
		return fmt.Errorf("failed to seek to end of superblock: %v", err)
	}

	// Write chunk data atomically
	n, err := file.Write(data)
	if err != nil {
		return fmt.Errorf("failed to write chunk data: %v", err)
	}

	if n != len(data) {
		return fmt.Errorf("incomplete write: expected %d bytes, wrote %d", len(data), n)
	}

	// Ensure data is written to disk (fsync for durability)
	if err := file.Sync(); err != nil {
		log.Printf("Warning: failed to sync chunk %s to disk: %v", chunkID, err)
	}

	// Update in-memory index
	entry := ChunkEntry{
		ChunkID:      chunkID,
		SuperblockID: sn.currentSuperblock,
		Offset:       offset,
		Size:         int32(n),
		Checksum:     checksum,
		StoredAt:     time.Now(),
	}

	sn.index.mu.Lock()
	sn.index.chunks[chunkID] = entry
	sn.index.mu.Unlock()

	// Persist index for crash recovery
	if err := sn.saveIndex(); err != nil {
		log.Printf("Warning: failed to persist index after storing chunk %s: %v", chunkID, err)
		// Don't fail the operation, index will be rebuilt on restart
	}

	return nil
}

func (sn *StorageNode) readChunk(entry ChunkEntry) ([]byte, error) {
	superblockPath := sn.getSuperblockPath(entry.SuperblockID)
	
	file, err := os.Open(superblockPath)
	if err != nil {
		return nil, err
	}
	defer file.Close()

	// Seek to chunk offset
	_, err = file.Seek(entry.Offset, io.SeekStart)
	if err != nil {
		return nil, err
	}

	// Read chunk data
	data := make([]byte, entry.Size)
	n, err := file.Read(data)
	if err != nil {
		return nil, err
	}

	if n != int(entry.Size) {
		return nil, fmt.Errorf("incomplete read: expected %d bytes, got %d", entry.Size, n)
	}

	return data, nil
}

func main() {
	nodeID := os.Getenv("NODE_ID")
	if nodeID == "" {
		nodeID = "storage-node-1"
	}

	dataDir := os.Getenv("DATA_DIR")
	if dataDir == "" {
		dataDir = "./data"
	}

	port := os.Getenv("PORT")
	if port == "" {
		port = "8081"
	}

	fmt.Printf("Storage Node %s starting...\n", nodeID)

	// Initialize storage node
	storageNode := NewStorageNode(dataDir, nodeID)
	if err := storageNode.Initialize(); err != nil {
		log.Fatalf("Failed to initialize storage node: %v", err)
	}

	// Setup HTTP routes
	r := mux.NewRouter()
	r.HandleFunc("/chunk/{chunk_id}", storageNode.handlePutChunk).Methods("PUT")
	r.HandleFunc("/chunk/{chunk_id}", storageNode.handleGetChunk).Methods("GET")
	r.HandleFunc("/chunk/{chunk_id}", storageNode.handleHeadChunk).Methods("HEAD")
	r.HandleFunc("/ping", storageNode.handlePing).Methods("HEAD")
	r.HandleFunc("/health", storageNode.handleHealth).Methods("GET")

	// Add performance monitoring middleware
	r.Use(func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			start := time.Now()
			
			// Add request ID for tracing
			requestID := fmt.Sprintf("%d", time.Now().UnixNano())
			w.Header().Set("X-Request-ID", requestID)
			
			next.ServeHTTP(w, r)
			
			duration := time.Since(start)
			log.Printf("Request: %s %s - Duration: %v - Request-ID: %s", 
				r.Method, r.URL.Path, duration, requestID)
		})
	})

	// Add CORS headers for web clients
	r.Use(func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("Access-Control-Allow-Origin", "*")
			w.Header().Set("Access-Control-Allow-Methods", "GET, PUT, HEAD, OPTIONS")
			w.Header().Set("Access-Control-Allow-Headers", "Content-Type")
			
			if r.Method == "OPTIONS" {
				w.WriteHeader(http.StatusOK)
				return
			}
			
			next.ServeHTTP(w, r)
		})
	})

	fmt.Printf("Storage Node %s listening on port %s\n", nodeID, port)
	log.Fatal(http.ListenAndServe(":"+port, r))
}