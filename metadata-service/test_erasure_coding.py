#!/usr/bin/env python3
"""
Tests for Reed-Solomon erasure coding implementation
"""

import pytest
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from erasure_coding import ErasureCoder, FragmentManager

class TestErasureCoder:
    """Test Reed-Solomon erasure coding"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.coder = ErasureCoder(data_shards=3, parity_shards=2)
        self.test_data = b"Hello World! " * 1000  # ~13KB test data
    
    def test_encode_chunk(self):
        """Test encoding chunk into fragments"""
        fragments = self.coder.encode_chunk(self.test_data)
        
        # Should produce 5 fragments (3 data + 2 parity)
        assert len(fragments) == 5
        
        # All fragments should have data
        for frag in fragments:
            assert len(frag) > 0
        
        print(f"✓ Encoded {len(self.test_data)} bytes into {len(fragments)} fragments")
    
    def test_decode_with_all_fragments(self):
        """Test decoding with all fragments available"""
        # Encode
        fragments = self.coder.encode_chunk(self.test_data)
        
        # Decode with all fragments
        indices = list(range(5))
        decoded = self.coder.decode_fragments(fragments, indices)
        
        # Should recover original data
        assert decoded[:len(self.test_data)] == self.test_data
        print(f"✓ Successfully decoded with all {len(fragments)} fragments")
    
    def test_decode_with_minimum_fragments(self):
        """Test decoding with minimum required fragments (3 out of 5)"""
        # Encode
        fragments = self.coder.encode_chunk(self.test_data)
        
        # Use only first 3 fragments (minimum required)
        partial_fragments = fragments[:3]
        indices = [0, 1, 2]
        
        # Decode
        decoded = self.coder.decode_fragments(partial_fragments, indices)
        
        # Should recover original data
        assert decoded[:len(self.test_data)] == self.test_data
        print(f"✓ Successfully decoded with minimum {len(partial_fragments)} fragments")
    
    def test_decode_with_different_fragment_combinations(self):
        """Test decoding with various fragment combinations"""
        # Encode
        fragments = self.coder.encode_chunk(self.test_data)
        
        # Test different combinations of 3 fragments
        combinations = [
            ([0, 1, 2], "first three"),
            ([0, 2, 4], "fragments 0,2,4"),
            ([1, 3, 4], "fragments 1,3,4"),
            ([2, 3, 4], "last three")
        ]
        
        for indices, desc in combinations:
            selected_frags = [fragments[i] for i in indices]
            decoded = self.coder.decode_fragments(selected_frags, indices)
            assert decoded[:len(self.test_data)] == self.test_data
            print(f"✓ Decoded successfully with {desc}")
    
    def test_insufficient_fragments_error(self):
        """Test that decoding fails with insufficient fragments"""
        # Encode
        fragments = self.coder.encode_chunk(self.test_data)
        
        # Try with only 2 fragments (need 3)
        with pytest.raises(ValueError, match="Insufficient fragments"):
            self.coder.decode_fragments(fragments[:2], [0, 1])
        
        print("✓ Correctly raises error with insufficient fragments")
    
    def test_fragment_checksum(self):
        """Test fragment checksum calculation"""
        fragments = self.coder.encode_chunk(self.test_data)
        
        for i, frag in enumerate(fragments):
            checksum = self.coder.get_fragment_checksum(frag)
            assert len(checksum) == 64  # SHA-256 hex is 64 chars
            
            # Verify checksum
            assert self.coder.verify_fragment(frag, checksum)
        
        print(f"✓ Fragment checksums verified for {len(fragments)} fragments")
    
    def test_storage_efficiency(self):
        """Test storage efficiency calculation"""
        efficiency = self.coder.get_storage_efficiency()
        
        # Should save ~67% compared to 3x replication
        # Erasure: 5/3 = 1.67x vs Replication: 3x
        # Savings: (3 - 1.67) / 3 = 0.44 = 44%
        assert efficiency > 0.4  # At least 40% savings
        assert efficiency < 0.5  # Less than 50% savings
        
        print(f"✓ Storage efficiency: {efficiency*100:.1f}% savings")
    
    def test_large_chunk(self):
        """Test with realistic 2MB chunk size"""
        # Create 2MB test data
        large_data = b"X" * (2 * 1024 * 1024)
        
        # Encode
        fragments = self.coder.encode_chunk(large_data)
        assert len(fragments) == 5
        
        # Verify total encoded size is reasonable
        total_encoded_size = sum(len(frag) for frag in fragments)
        original_size = len(large_data)
        
        # Total encoded should be larger than original (due to parity)
        # but not excessively large (< 2x original)
        assert total_encoded_size > original_size
        assert total_encoded_size < original_size * 2
        
        # Decode with minimum fragments
        decoded = self.coder.decode_fragments(fragments[:3], [0, 1, 2])
        assert decoded[:len(large_data)] == large_data
        
        frag_sizes = [len(f)/1024 for f in fragments]
        print(f"✓ Successfully handled 2MB chunk (fragments: {frag_sizes[0]:.0f}KB each)")


class TestFragmentManager:
    """Test fragment management functionality"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.coder = ErasureCoder(data_shards=3, parity_shards=2)
        self.manager = FragmentManager(self.coder)
        self.test_data = b"Test data " * 100
    
    def test_create_fragment_metadata(self):
        """Test fragment metadata creation"""
        chunk_id = "test-chunk-001"
        fragments = self.coder.encode_chunk(self.test_data)
        
        metadata = self.manager.create_fragment_metadata(chunk_id, fragments)
        
        assert len(metadata) == 5
        
        for i, meta in enumerate(metadata):
            assert meta["fragment_id"] == f"{chunk_id}-frag-{i}"
            assert meta["chunk_id"] == chunk_id
            assert meta["fragment_index"] == i
            assert meta["size_bytes"] > 0
            assert len(meta["checksum"]) == 64
        
        print(f"✓ Created metadata for {len(metadata)} fragments")
    
    def test_reconstruct_chunk(self):
        """Test chunk reconstruction from fragments"""
        chunk_id = "test-chunk-002"
        fragments = self.coder.encode_chunk(self.test_data)
        
        # Simulate storing fragments with indices
        fragment_tuples = [(i, frag) for i, frag in enumerate(fragments[:3])]
        
        # Reconstruct
        reconstructed = self.manager.reconstruct_chunk(fragment_tuples)
        
        assert reconstructed[:len(self.test_data)] == self.test_data
        print("✓ Successfully reconstructed chunk from fragments")
    
    def test_reconstruct_with_missing_fragments(self):
        """Test reconstruction with some fragments missing"""
        chunk_id = "test-chunk-003"
        fragments = self.coder.encode_chunk(self.test_data)
        
        # Simulate fragments 0, 2, 4 available (1, 3 missing)
        fragment_tuples = [
            (0, fragments[0]),
            (2, fragments[2]),
            (4, fragments[4])
        ]
        
        # Reconstruct
        reconstructed = self.manager.reconstruct_chunk(fragment_tuples)
        
        assert reconstructed[:len(self.test_data)] == self.test_data
        print("✓ Reconstructed chunk with missing fragments")


def run_tests():
    """Run all tests"""
    print("\n" + "="*60)
    print("Testing Reed-Solomon Erasure Coding")
    print("="*60 + "\n")
    
    # Test ErasureCoder
    print("Testing ErasureCoder...")
    test_coder = TestErasureCoder()
    
    test_coder.setup_method()
    test_coder.test_encode_chunk()
    
    test_coder.setup_method()
    test_coder.test_decode_with_all_fragments()
    
    test_coder.setup_method()
    test_coder.test_decode_with_minimum_fragments()
    
    test_coder.setup_method()
    test_coder.test_decode_with_different_fragment_combinations()
    
    test_coder.setup_method()
    test_coder.test_insufficient_fragments_error()
    
    test_coder.setup_method()
    test_coder.test_fragment_checksum()
    
    test_coder.setup_method()
    test_coder.test_storage_efficiency()
    
    test_coder.setup_method()
    test_coder.test_large_chunk()
    
    print("\nTesting FragmentManager...")
    test_manager = TestFragmentManager()
    
    test_manager.setup_method()
    test_manager.test_create_fragment_metadata()
    
    test_manager.setup_method()
    test_manager.test_reconstruct_chunk()
    
    test_manager.setup_method()
    test_manager.test_reconstruct_with_missing_fragments()
    
    print("\n" + "="*60)
    print("All tests passed! ✓")
    print("="*60 + "\n")


if __name__ == "__main__":
    run_tests()
