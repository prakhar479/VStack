package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"regexp"
	"runtime/debug"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"syscall"
	"time"

	"github.com/gorilla/mux"
)

// Constants for configuration and validation
const (
	// Storage configuration
	DefaultMaxSuperblockSize = 1 * 1024 * 1024 * 1024 // 1GB
	MaxChunkSize             = 2 * 1024 * 1024        // 2MB
	MaxChunkSizeBuffer       = MaxChunkSize + 1024    // Allow overhead for headers

	// Performance requirements
	MaxRetrievalLatency = 10 * time.Millisecond

	// Health thresholds
	DiskUsageWarningThreshold  = 85.0
	DiskUsageCriticalThreshold = 95.0

	// Error messages
	ErrInsufficientStorage = "Insufficient storage space"
	ErrChunkNotFound       = "Chunk not found"
	ErrInvalidChunkID      = "Invalid chunk ID format"
	ErrChecksumMismatch    = "Checksum mismatch"

	// Retry configuration
	MaxRegistrationRetries = 12
	RegistrationTimeout    = 2 * time.Minute
	RetryInterval          = 5 * time.Second

	// Server timeouts
	ServerReadTimeout  = 15 * time.Second
	ServerWriteTimeout = 15 * time.Second
	ServerIdleTimeout  = 60 * time.Second
)

var (
	// validChunkID validates chunk ID format (alphanumeric, underscore, hyphen, 1-64 chars)
	validChunkID = regexp.MustCompile(`^[a-zA-Z0-9_-]{1,64}$`)
)

// validateChunkID validates the format of a chunk ID
func validateChunkID(id string) error {
	if !validChunkID.MatchString(id) {
		return fmt.Errorf(ErrInvalidChunkID)
	}
	return nil
}

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
	Version    uint32    `json:"version"`
	ChunkCount uint32    `json:"chunk_count"`
	NextOffset int64     `json:"next_offset"`
	CreatedAt  time.Time `json:"created_at"`
}

// StorageNode represents the main storage node server
type StorageNode struct {
	dataDir           string
	indexFile         string
	index             *ChunkIndex
	currentSuperblock int
	maxSuperblockSize int64
	nodeID            string
	mu                sync.Mutex
	startTime         time.Time
	failedIndexSaves  int64 // atomic counter for failed index save operations
}

// HealthResponse represents the health check response
type HealthResponse struct {
	Status     string  `json:"status"`
	DiskUsage  float64 `json:"disk_usage"`
	ChunkCount int     `json:"chunk_count"`
	Uptime     int64   `json:"uptime"`
	NodeID     string  `json:"node_id"`
}

func NewStorageNode(dataDir, nodeID string) *StorageNode {
	// Parse max superblock size from environment with default
	maxSize := int64(DefaultMaxSuperblockSize)
	if envSize := os.Getenv("MAX_SUPERBLOCK_SIZE_MB"); envSize != "" {
		if sizeMB, err := strconv.ParseInt(envSize, 10, 64); err == nil && sizeMB > 0 {
			maxSize = sizeMB * 1024 * 1024
			log.Printf("Using custom superblock size: %d MB", sizeMB)
		}
	}

	return &StorageNode{
		dataDir:           dataDir,
		indexFile:         filepath.Join(dataDir, "index", "chunk_index.json"),
		index:             &ChunkIndex{chunks: make(map[string]ChunkEntry)},
		currentSuperblock: 0,
		maxSuperblockSize: maxSize,
		nodeID:            nodeID,
		startTime:         time.Now(),
		failedIndexSaves:  0,
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
			return fmt.Errorf("failed to create directory %s: %w", dir, err)
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
		return fmt.Errorf("failed to open index file: %w", err)
	}
	defer file.Close()

	return json.NewDecoder(file).Decode(&sn.index.chunks)
}

func (sn *StorageNode) saveIndex() error {
	sn.index.mu.RLock()
	defer sn.index.mu.RUnlock()

	// Write to temporary file first (atomic write pattern)
	tempFile := sn.indexFile + ".tmp"
	file, err := os.Create(tempFile)
	if err != nil {
		atomic.AddInt64(&sn.failedIndexSaves, 1)
		return fmt.Errorf("failed to create temp index file: %w", err)
	}

	if err := json.NewEncoder(file).Encode(sn.index.chunks); err != nil {
		file.Close()
		os.Remove(tempFile)
		atomic.AddInt64(&sn.failedIndexSaves, 1)
		return fmt.Errorf("failed to encode index: %w", err)
	}

	if err := file.Sync(); err != nil {
		file.Close()
		os.Remove(tempFile)
		atomic.AddInt64(&sn.failedIndexSaves, 1)
		return fmt.Errorf("failed to sync index: %w", err)
	}
	file.Close()

	// Atomic rename
	if err := os.Rename(tempFile, sn.indexFile); err != nil {
		os.Remove(tempFile)
		atomic.AddInt64(&sn.failedIndexSaves, 1)
		return fmt.Errorf("failed to rename index file: %w", err)
	}

	// Reset failure counter on success
	atomic.StoreInt64(&sn.failedIndexSaves, 0)
	return nil
}

func (sn *StorageNode) findCurrentSuperblock() {
	dataDir := filepath.Join(sn.dataDir, "data")
	files, err := os.ReadDir(dataDir)
	if err != nil {
		log.Printf("Warning: failed to read data dir: %v", err)
		return
	}

	maxID := -1
	for _, file := range files {
		if strings.HasPrefix(file.Name(), "superblock_") && strings.HasSuffix(file.Name(), ".dat") {
			idStr := strings.TrimPrefix(file.Name(), "superblock_")
			idStr = strings.TrimSuffix(idStr, ".dat")
			if id, err := strconv.Atoi(idStr); err == nil && id > maxID {
				// Validate file is readable and appears valid
				path := sn.getSuperblockPath(id)
				if info, err := os.Stat(path); err == nil && info.Mode().IsRegular() {
					maxID = id
				}
			}
		}
	}

	if maxID >= 0 {
		sn.currentSuperblock = maxID
		log.Printf("Found existing superblock: %d", maxID)
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
		return 0, fmt.Errorf("failed to stat superblock: %w", err)
	}
	return info.Size(), nil
}

func (sn *StorageNode) getDiskUsage() float64 {
	var stat syscall.Statfs_t
	if err := syscall.Statfs(sn.dataDir, &stat); err != nil {
		log.Printf("Warning: failed to get disk usage: %v", err)
		return 0.0
	}

	total := stat.Blocks * uint64(stat.Bsize)
	free := stat.Bavail * uint64(stat.Bsize)
	used := total - free

	return float64(used) / float64(total) * 100.0
}

func (sn *StorageNode) Shutdown() {
	log.Println("Shutting down storage node...")

	//  Save index without holding lock
	if err := sn.saveIndex(); err != nil {
		log.Printf("Failed to save index during shutdown: %v", err)
	} else {
		log.Println("Index saved successfully")
	}

	log.Println("Storage Node shutdown complete")
}

// HTTP Handlers

func (sn *StorageNode) handlePutChunk(w http.ResponseWriter, r *http.Request) {
	vars := mux.Vars(r)
	chunkID := vars["chunk_id"]

	if chunkID == "" {
		http.Error(w, "chunk_id is required", http.StatusBadRequest)
		return
	}

	// Validate chunk ID format
	if err := validateChunkID(chunkID); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
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

	// Validate content length (early rejection)
	contentLength := r.ContentLength
	if contentLength <= 0 {
		http.Error(w, "Content-Length header required", http.StatusBadRequest)
		return
	}
	if contentLength > MaxChunkSizeBuffer {
		http.Error(w, fmt.Sprintf("Chunk size exceeds maximum allowed (%d bytes)", MaxChunkSize), http.StatusRequestEntityTooLarge)
		return
	}

	// Read chunk data with size limit
	data, err := io.ReadAll(io.LimitReader(r.Body, MaxChunkSizeBuffer))
	if err != nil {
		http.Error(w, "Failed to read chunk data", http.StatusBadRequest)
		return
	}

	if len(data) == 0 {
		http.Error(w, "Empty chunk data", http.StatusBadRequest)
		return
	}

	// Compute checksum for integrity
	hash := sha256.Sum256(data)
	computedChecksum := hex.EncodeToString(hash[:])

	// Validate against client-provided checksum if present
	clientChecksum := r.Header.Get("X-Chunk-Checksum")
	if clientChecksum != "" && clientChecksum != computedChecksum {
		http.Error(w, ErrChecksumMismatch, http.StatusBadRequest)
		return
	}

	// Store chunk with proper error handling
	if err := sn.storeChunk(chunkID, data, computedChecksum); err != nil {
		if strings.Contains(err.Error(), "insufficient storage") {
			http.Error(w, ErrInsufficientStorage, http.StatusInsufficientStorage)
		} else {
			log.Printf("Storage error for chunk %s: %v", chunkID, err)
			http.Error(w, "Internal storage error", http.StatusInternalServerError)
		}
		return
	}

	// Success response with proper headers
	w.Header().Set("Location", fmt.Sprintf("/chunk/%s", chunkID))
	w.Header().Set("ETag", computedChecksum)
	w.Header().Set("X-Chunk-Size", strconv.Itoa(len(data)))
	w.WriteHeader(http.StatusCreated)

	log.Printf("Stored chunk %s (size: %d bytes, checksum: %s)", chunkID, len(data), computedChecksum[:16]+"...")
}

func (sn *StorageNode) handleGetChunk(w http.ResponseWriter, r *http.Request) {
	requestStart := time.Now()
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
		http.Error(w, ErrChunkNotFound, http.StatusNotFound)
		return
	}

	// Read chunk data with direct I/O for performance
	data, err := sn.readChunk(entry)
	if err != nil {
		log.Printf("Failed to read chunk %s: %v", chunkID, err)
		http.Error(w, "Failed to read chunk", http.StatusInternalServerError)
		return
	}

	// Verify checksum for data integrity
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
	if _, err := w.Write(data); err != nil {
		log.Printf("Failed to write response for chunk %s: %v", chunkID, err)
	}

	//  Log performance metrics
	duration := time.Since(requestStart)
	if duration > MaxRetrievalLatency {
		log.Printf("WARNING: Chunk retrieval for %s took %v (exceeds 10ms requirement)", chunkID, duration)
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
		http.Error(w, ErrChunkNotFound, http.StatusNotFound)
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
}

func (sn *StorageNode) handleDeleteChunk(w http.ResponseWriter, r *http.Request) {
	vars := mux.Vars(r)
	chunkID := vars["chunk_id"]

	if chunkID == "" {
		http.Error(w, "chunk_id is required", http.StatusBadRequest)
		return
	}

	// Remove from index
	sn.index.mu.Lock()
	_, exists := sn.index.chunks[chunkID]
	if exists {
		delete(sn.index.chunks, chunkID)
	}
	sn.index.mu.Unlock()

	if !exists {
		http.Error(w, ErrChunkNotFound, http.StatusNotFound)
		return
	}

	// Persist index (best effort)
	if err := sn.saveIndex(); err != nil {
		log.Printf("Warning: failed to persist index after deleting chunk %s: %v", chunkID, err)
	}

	// Note: Actual data remains in superblock file - would need garbage collection
	w.WriteHeader(http.StatusNoContent)
	log.Printf("Deleted chunk %s from index", chunkID)
}

func (sn *StorageNode) handlePing(w http.ResponseWriter, r *http.Request) {
	pingStart := time.Now()

	diskUsage := sn.getDiskUsage()

	sn.index.mu.RLock()
	chunkCount := len(sn.index.chunks)
	sn.index.mu.RUnlock()

	// Set headers for client monitoring
	w.Header().Set("X-Node-ID", sn.nodeID)
	w.Header().Set("X-Disk-Usage-Percent", fmt.Sprintf("%.2f", diskUsage))
	w.Header().Set("X-Chunk-Count", strconv.Itoa(chunkCount))
	w.Header().Set("X-Response-Time", fmt.Sprintf("%.3f", time.Since(pingStart).Seconds()*1000)) // ms
	w.Header().Set("Cache-Control", "no-cache")

	w.WriteHeader(http.StatusOK)
}

func (sn *StorageNode) handleHealth(w http.ResponseWriter, r *http.Request) {
	sn.index.mu.RLock()
	chunkCount := len(sn.index.chunks)
	sn.index.mu.RUnlock()

	uptime := time.Since(sn.startTime).Seconds()
	diskUsage := sn.getDiskUsage()
	failedSaves := atomic.LoadInt64(&sn.failedIndexSaves)

	// Determine health status
	status := "healthy"
	if diskUsage > DiskUsageCriticalThreshold || failedSaves > 5 {
		status = "critical"
	} else if diskUsage > DiskUsageWarningThreshold || failedSaves > 0 {
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

	if err := json.NewEncoder(w).Encode(health); err != nil {
		log.Printf("Failed to encode health response: %v", err)
	}
}

func (sn *StorageNode) storeChunk(chunkID string, data []byte, checksum string) error {
	sn.mu.Lock()
	defer sn.mu.Unlock()

	// Check available disk space
	diskUsage := sn.getDiskUsage()
	if diskUsage > DiskUsageCriticalThreshold {
		return fmt.Errorf("insufficient storage space: disk usage %.2f%%", diskUsage)
	}

	// Check if current superblock has space
	currentSize, err := sn.getCurrentSuperblockSize()
	if err != nil {
		return fmt.Errorf("failed to get superblock size: %w", err)
	}

	// Rotate to new superblock if current one would exceed limit
	if currentSize+int64(len(data)) > sn.maxSuperblockSize {
		sn.currentSuperblock++
		log.Printf("Rotating to new superblock %d (current size: %d bytes)", sn.currentSuperblock, currentSize)
	}

	// Open/create superblock file
	superblockPath := sn.getSuperblockPath(sn.currentSuperblock)
	file, err := os.OpenFile(superblockPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0644)
	if err != nil {
		return fmt.Errorf("failed to open superblock file %s: %w", superblockPath, err)
	}
	defer file.Close()

	// Get current offset for direct I/O positioning
	offset, err := file.Seek(0, io.SeekEnd)
	if err != nil {
		return fmt.Errorf("failed to seek to end of superblock: %w", err)
	}

	// Write chunk data atomically
	n, err := file.Write(data)
	if err != nil {
		return fmt.Errorf("failed to write chunk data: %w", err)
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

	// Persist index for crash recovery (best effort)
	if err := sn.saveIndex(); err != nil {
		log.Printf("Warning: failed to persist index after storing chunk %s: %v", chunkID, err)
	}

	return nil
}

func (sn *StorageNode) readChunk(entry ChunkEntry) ([]byte, error) {
	superblockPath := sn.getSuperblockPath(entry.SuperblockID)

	file, err := os.Open(superblockPath)
	if err != nil {
		return nil, fmt.Errorf("failed to open superblock: %w", err)
	}
	defer file.Close()

	// Seek to chunk offset
	_, err = file.Seek(entry.Offset, io.SeekStart)
	if err != nil {
		return nil, fmt.Errorf("failed to seek to chunk offset: %w", err)
	}

	// Read chunk data
	data := make([]byte, entry.Size)
	n, err := file.Read(data)
	if err != nil {
		return nil, fmt.Errorf("failed to read chunk data: %w", err)
	}

	if n != int(entry.Size) {
		return nil, fmt.Errorf("incomplete read: expected %d bytes, got %d", entry.Size, n)
	}

	return data, nil
}

func (sn *StorageNode) registerNode(ctx context.Context, metadataURL, nodeURL string) error {
	// Prepare registration data
	regData := map[string]string{
		"node_url": nodeURL,
		"node_id":  sn.nodeID,
		"version":  "1.0.0",
	}
	body, err := json.Marshal(regData)
	if err != nil {
		return fmt.Errorf("failed to marshal registration data: %w", err)
	}

	url := fmt.Sprintf("%s/nodes/register", metadataURL)
	req, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("failed to create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return fmt.Errorf("registration request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("registration failed with status: %d", resp.StatusCode)
	}

	return nil
}

func main() {
	// Parse command line arguments or environment variables
	portStr := os.Getenv("PORT")
	if portStr == "" {
		portStr = "8081"
	}
	port, err := strconv.Atoi(portStr)
	if err != nil || port < 1 || port > 65535 {
		log.Fatalf("Invalid PORT value '%s': must be between 1-65535", portStr)
	}

	dataDir := os.Getenv("DATA_DIR")
	if dataDir == "" {
		dataDir = "./data"
	}

	nodeID := os.Getenv("NODE_ID")
	if nodeID == "" {
		nodeID = fmt.Sprintf("node-%d", port)
	}

	// Create storage node
	sn := NewStorageNode(dataDir, nodeID)

	if err := sn.Initialize(); err != nil {
		log.Fatalf("Failed to initialize storage node: %v", err)
	}

	// Setup router
	r := mux.NewRouter()

	// Panic recovery middleware
	r.Use(func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			defer func() {
				if err := recover(); err != nil {
					log.Printf("PANIC: %v\n%s", err, debug.Stack())
					http.Error(w, "Internal server error", http.StatusInternalServerError)
				}
			}()
			next.ServeHTTP(w, r)
		})
	})

	// Request logging middleware
	r.Use(func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			start := time.Now()
			requestID := fmt.Sprintf("%d", time.Now().UnixNano())
			w.Header().Set("X-Request-ID", requestID)
			next.ServeHTTP(w, r)
			duration := time.Since(start)
			log.Printf("Request: %s %s - Duration: %v - Request-ID: %s",
				r.Method, r.URL.Path, duration, requestID)
		})
	})

	// CORS middleware
	r.Use(func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			allowedOrigin := os.Getenv("ALLOWED_ORIGIN")
			if allowedOrigin == "" {
				allowedOrigin = "*" // Default for development
			}
			w.Header().Set("Access-Control-Allow-Origin", allowedOrigin)
			w.Header().Set("Access-Control-Allow-Methods", "GET, PUT, DELETE, HEAD, OPTIONS")
			w.Header().Set("Access-Control-Allow-Headers", "Content-Type, X-Chunk-Checksum")
			if r.Method == "OPTIONS" {
				w.WriteHeader(http.StatusOK)
				return
			}
			next.ServeHTTP(w, r)
		})
	})

	// API Endpoints
	r.HandleFunc("/chunk/{chunk_id}", sn.handlePutChunk).Methods("PUT")
	r.HandleFunc("/chunk/{chunk_id}", sn.handleGetChunk).Methods("GET")
	r.HandleFunc("/chunk/{chunk_id}", sn.handleHeadChunk).Methods("HEAD")
	r.HandleFunc("/chunk/{chunk_id}", sn.handleDeleteChunk).Methods("DELETE")
	r.HandleFunc("/ping", sn.handlePing).Methods("HEAD", "GET")
	r.HandleFunc("/health", sn.handleHealth).Methods("GET")

	srv := &http.Server{
		Addr:         fmt.Sprintf(":%d", port),
		Handler:      r,
		ReadTimeout:  ServerReadTimeout,
		WriteTimeout: ServerWriteTimeout,
		IdleTimeout:  ServerIdleTimeout,
	}

	// Create context for graceful shutdown
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()

	// Register with metadata service in background
	var wg sync.WaitGroup
	wg.Add(1)
	go func() {
		defer wg.Done()

		// Wait for service to start
		time.Sleep(2 * time.Second)

		metadataURL := os.Getenv("METADATA_SERVICE_URL")
		nodeURL := os.Getenv("NODE_URL")

		if metadataURL == "" || nodeURL == "" {
			log.Printf("Warning: METADATA_SERVICE_URL or NODE_URL not set, skipping registration")
			return
		}

		// Create context with timeout for registration
		regCtx, regCancel := context.WithTimeout(ctx, RegistrationTimeout)
		defer regCancel()

		for i := 0; i < MaxRegistrationRetries; i++ {
			if err := sn.registerNode(regCtx, metadataURL, nodeURL); err != nil {
				log.Printf("Failed to register (attempt %d/%d): %v", i+1, MaxRegistrationRetries, err)
				select {
				case <-regCtx.Done():
					log.Println("Registration timeout, continuing without registration")
					return
				case <-time.After(RetryInterval):
					continue
				}
			} else {
				log.Printf("Successfully registered node %s with metadata service at %s", nodeID, metadataURL)
				break
			}
		}
	}()

	// Run server in goroutine
	go func() {
		log.Printf("Storage Node %s listening on port %d", nodeID, port)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("Server failed: %v", err)
		}
	}()

	// Wait for interrupt signal
	<-ctx.Done()

	// Graceful shutdown
	log.Println("Shutdown signal received")
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer shutdownCancel()

	if err := srv.Shutdown(shutdownCtx); err != nil {
		log.Printf("Server forced to shutdown: %v", err)
	}

	// Wait for registration goroutine
	wg.Wait()

	sn.Shutdown()
	log.Println("Storage Node exited properly")
}
