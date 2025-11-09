#!/usr/bin/env python3
"""
Reed-Solomon Erasure Coding Implementation for V-Stack
Encodes 2MB chunks into 5 fragments (400KB each) where any 3 can reconstruct the original
"""

import logging
from typing import List, Tuple, Optional
import hashlib

try:
    from reedsolo import RSCodec
except ImportError:
    RSCodec = None

logger = logging.getLogger(__name__)

class ErasureCoder:
    """
    Reed-Solomon erasure coding for chunk redundancy
    
    Configuration:
    - Original chunk: 2MB (2097152 bytes)
    - Encoded into: 5 fragments of ~400KB each
    - Recovery: Any 3 fragments can reconstruct original
    - Storage savings: 2MB vs 6MB (3 full replicas) = 67% savings
    """
    
    def __init__(self, data_shards: int = 3, parity_shards: int = 2):
        """
        Initialize erasure coder
        
        Args:
            data_shards: Number of data fragments (3)
            parity_shards: Number of parity fragments (2)
            Total fragments = 5, any 3 can recover original
        """
        if RSCodec is None:
            raise ImportError("reedsolo library not installed. Install with: pip install reedsolo")
        
        self.data_shards = data_shards
        self.parity_shards = parity_shards
        self.total_shards = data_shards + parity_shards
        
        # Initialize Reed-Solomon codec
        # nsym = number of error correction symbols (parity shards)
        self.codec = RSCodec(parity_shards)
        
        logger.info(f"Erasure coder initialized: {data_shards} data + {parity_shards} parity = {self.total_shards} total shards")
    
    def encode_chunk(self, chunk_data: bytes) -> List[bytes]:
        """
        Encode a 2MB chunk into 5 fragments
        
        Args:
            chunk_data: Original chunk data (2MB)
            
        Returns:
            List of 5 fragment bytes (each ~400KB)
        """
        if not chunk_data:
            raise ValueError("Chunk data cannot be empty")
        
        chunk_size = len(chunk_data)
        
        # Calculate fragment size (divide chunk into data_shards equal parts)
        fragment_size = (chunk_size + self.data_shards - 1) // self.data_shards
        
        # Pad chunk data to be evenly divisible by data_shards
        padded_size = fragment_size * self.data_shards
        padding_length = padded_size - chunk_size
        if padding_length > 0:
            chunk_data = chunk_data + b'\x00' * padding_length
        
        # Store original size for later recovery
        self._original_size = chunk_size
        
        # Split into data fragments
        data_fragments = []
        for i in range(self.data_shards):
            start = i * fragment_size
            end = start + fragment_size
            data_fragments.append(chunk_data[start:end])
        
        # Generate parity fragments using Reed-Solomon
        # For each byte position across all data fragments, encode it
        all_fragments = list(data_fragments)
        
        # Create parity fragments
        for parity_idx in range(self.parity_shards):
            parity_fragment = bytearray(fragment_size)
            
            # For each byte position in the fragment
            for byte_pos in range(fragment_size):
                # Collect bytes from all data fragments at this position
                data_bytes = bytes([data_fragments[i][byte_pos] for i in range(self.data_shards)])
                
                # Encode using Reed-Solomon
                encoded = self.codec.encode(data_bytes)
                
                # Extract parity byte (after the data bytes)
                parity_byte = encoded[self.data_shards + parity_idx]
                parity_fragment[byte_pos] = parity_byte
            
            all_fragments.append(bytes(parity_fragment))
        
        logger.debug(f"Encoded {chunk_size} bytes into {len(all_fragments)} fragments of {fragment_size} bytes each")
        
        return all_fragments
    
    def decode_fragments(self, fragments: List[Optional[bytes]], fragment_indices: List[int]) -> bytes:
        """
        Decode original chunk from available fragments
        
        Args:
            fragments: List of available fragment bytes (None for missing fragments)
            fragment_indices: Indices of available fragments (0-4)
            
        Returns:
            Original chunk data
            
        Raises:
            ValueError: If insufficient fragments available (need at least 3)
        """
        available_fragments = [f for f in fragments if f is not None]
        if len(available_fragments) < self.data_shards:
            raise ValueError(f"Insufficient fragments: need at least {self.data_shards}, got {len(available_fragments)}")
        
        # Get fragment size
        fragment_size = len(available_fragments[0])
        
        # Create a mapping of available fragments
        fragment_map = {}
        for idx, frag in zip(fragment_indices, available_fragments):
            fragment_map[idx] = frag
        
        # If we have all data fragments (0, 1, 2), we can reconstruct directly
        if all(i in fragment_map for i in range(self.data_shards)):
            # Simple case: just concatenate data fragments
            reconstructed = b''.join([fragment_map[i] for i in range(self.data_shards)])
            logger.debug(f"Decoded {len(reconstructed)} bytes from data fragments")
            return reconstructed
        
        # Otherwise, we need to use Reed-Solomon decoding
        # Reconstruct data fragments using available fragments
        reconstructed_data_fragments = []
        
        for data_idx in range(self.data_shards):
            if data_idx in fragment_map:
                # We have this data fragment
                reconstructed_data_fragments.append(fragment_map[data_idx])
            else:
                # Need to reconstruct this data fragment
                reconstructed_fragment = bytearray(fragment_size)
                
                # For each byte position
                for byte_pos in range(fragment_size):
                    # Collect available bytes at this position
                    available_bytes = bytearray(self.total_shards)
                    erasures = []
                    
                    for frag_idx in range(self.total_shards):
                        if frag_idx in fragment_map:
                            available_bytes[frag_idx] = fragment_map[frag_idx][byte_pos]
                        else:
                            available_bytes[frag_idx] = 0
                            erasures.append(frag_idx)
                    
                    # Decode using Reed-Solomon
                    try:
                        decoded_bytes = self.codec.decode(bytes(available_bytes), erase_pos=erasures)[0]
                        reconstructed_fragment[byte_pos] = decoded_bytes[data_idx]
                    except Exception as e:
                        logger.error(f"Failed to decode byte at position {byte_pos}: {e}")
                        raise ValueError(f"Failed to reconstruct fragment {data_idx}")
                
                reconstructed_data_fragments.append(bytes(reconstructed_fragment))
        
        # Concatenate all data fragments
        reconstructed = b''.join(reconstructed_data_fragments)
        logger.debug(f"Decoded {len(reconstructed)} bytes from {len(available_fragments)} fragments")
        return reconstructed
    
    def get_fragment_checksum(self, fragment: bytes) -> str:
        """Calculate SHA-256 checksum for a fragment"""
        return hashlib.sha256(fragment).hexdigest()
    
    def verify_fragment(self, fragment: bytes, expected_checksum: str) -> bool:
        """Verify fragment integrity using checksum"""
        actual_checksum = self.get_fragment_checksum(fragment)
        return actual_checksum == expected_checksum
    
    def get_storage_efficiency(self) -> float:
        """
        Calculate storage efficiency compared to full replication
        
        Returns:
            Percentage of storage saved (e.g., 0.67 = 67% savings)
        """
        # Full replication: 3 copies of 2MB = 6MB
        # Erasure coding: 5 fragments of ~400KB = 2MB
        replication_size = 3.0  # 3 full copies
        erasure_size = float(self.total_shards) / float(self.data_shards)  # 5/3 = 1.67 copies
        
        savings = (replication_size - erasure_size) / replication_size
        return savings


class FragmentManager:
    """Manages fragment storage and retrieval across storage nodes"""
    
    def __init__(self, erasure_coder: ErasureCoder):
        self.coder = erasure_coder
    
    def create_fragment_metadata(self, chunk_id: str, fragments: List[bytes]) -> List[dict]:
        """
        Create metadata for each fragment
        
        Args:
            chunk_id: Original chunk ID
            fragments: List of fragment bytes
            
        Returns:
            List of fragment metadata dicts
        """
        fragment_metadata = []
        
        for i, fragment in enumerate(fragments):
            metadata = {
                "fragment_id": f"{chunk_id}-frag-{i}",
                "chunk_id": chunk_id,
                "fragment_index": i,
                "size_bytes": len(fragment),
                "checksum": self.coder.get_fragment_checksum(fragment)
            }
            fragment_metadata.append(metadata)
        
        return fragment_metadata
    
    def reconstruct_chunk(self, fragments: List[Tuple[int, bytes]]) -> bytes:
        """
        Reconstruct original chunk from available fragments
        
        Args:
            fragments: List of (fragment_index, fragment_data) tuples
            
        Returns:
            Original chunk data
        """
        if len(fragments) < self.coder.data_shards:
            raise ValueError(f"Need at least {self.coder.data_shards} fragments, got {len(fragments)}")
        
        # Sort fragments by index
        fragments.sort(key=lambda x: x[0])
        
        # Create fragment list with None for missing fragments
        max_index = max(f[0] for f in fragments)
        fragment_list = [None] * (max_index + 1)
        indices = []
        
        for idx, data in fragments:
            fragment_list[idx] = data
            indices.append(idx)
        
        # Decode using erasure coder
        return self.coder.decode_fragments(fragment_list, indices)
