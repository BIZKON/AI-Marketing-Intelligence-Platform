"""Content deduplication using SimHash.

SimHash produces a fingerprint where similar texts have similar hashes.
Two hashes with a Hamming distance <= threshold are considered near-duplicates.
"""

from __future__ import annotations

import re
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

# Number of bits in the SimHash fingerprint
SIMHASH_BITS = 64
# Hamming distance threshold for near-duplicate detection
HAMMING_THRESHOLD = 3


def _tokenize(text: str) -> list[str]:
    """Split text into lowercase word tokens."""
    text = text.lower()
    tokens = re.findall(r"\b\w{2,}\b", text)
    return tokens


def _hash_token(token: str) -> int:
    """FNV-1a 64-bit hash for a token."""
    h = 0xCBF29CE484222325
    for byte in token.encode("utf-8"):
        h ^= byte
        h = (h * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return h


def compute_simhash(text: str) -> str:
    """Compute a 64-bit SimHash fingerprint and return as hex string.

    Algorithm:
    1. Tokenize text into words
    2. Hash each token to 64-bit value
    3. For each bit position, sum +1 if bit is set, -1 if not
    4. Final fingerprint: bit is 1 if sum > 0, else 0
    """
    if not text or not text.strip():
        return "0" * 16  # 64 bits = 16 hex chars

    tokens = _tokenize(text)
    if not tokens:
        return "0" * 16

    # Build weighted bit vector
    bit_sums = [0] * SIMHASH_BITS

    # Count token frequencies for weighting
    freq: dict[str, int] = defaultdict(int)
    for t in tokens:
        freq[t] += 1

    seen: set[str] = set()
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        weight = freq[token]
        h = _hash_token(token)
        for i in range(SIMHASH_BITS):
            if h & (1 << i):
                bit_sums[i] += weight
            else:
                bit_sums[i] -= weight

    # Build fingerprint
    fingerprint = 0
    for i in range(SIMHASH_BITS):
        if bit_sums[i] > 0:
            fingerprint |= 1 << i

    return format(fingerprint, "016x")


def hamming_distance(hash_a: str, hash_b: str) -> int:
    """Compute the Hamming distance between two hex SimHash strings."""
    if not hash_a or not hash_b:
        return SIMHASH_BITS  # Maximum distance

    int_a = int(hash_a, 16)
    int_b = int(hash_b, 16)
    xor = int_a ^ int_b
    return bin(xor).count("1")


def is_near_duplicate(
    hash_a: str,
    hash_b: str,
    threshold: int = HAMMING_THRESHOLD,
) -> bool:
    """Check if two SimHash fingerprints are near-duplicates."""
    return hamming_distance(hash_a, hash_b) <= threshold


class DeduplicationIndex:
    """In-memory index for fast near-duplicate lookup.

    Uses bit-sampling to narrow candidates before computing exact distance.
    For production scale, consider persisting to Redis or DB.
    """

    def __init__(self, threshold: int = HAMMING_THRESHOLD) -> None:
        self.threshold = threshold
        self._hashes: dict[str, str] = {}  # external_id -> simhash
        # Bucket index: split 64-bit hash into 4x16-bit blocks
        self._buckets: list[dict[int, set[str]]] = [
            defaultdict(set) for _ in range(4)
        ]

    def add(self, external_id: str, simhash: str) -> None:
        """Add a hash to the index."""
        self._hashes[external_id] = simhash
        int_hash = int(simhash, 16)
        for band_idx in range(4):
            block = (int_hash >> (band_idx * 16)) & 0xFFFF
            self._buckets[band_idx][block].add(external_id)

    def find_duplicates(self, simhash: str) -> list[str]:
        """Find all external_ids that are near-duplicates of the given hash."""
        int_hash = int(simhash, 16)
        candidates: set[str] = set()

        # Gather candidates from bucket matches
        for band_idx in range(4):
            block = (int_hash >> (band_idx * 16)) & 0xFFFF
            candidates.update(self._buckets[band_idx].get(block, set()))

        # Verify with exact Hamming distance
        results = []
        for eid in candidates:
            if hamming_distance(self._hashes[eid], simhash) <= self.threshold:
                results.append(eid)

        return results

    def is_duplicate(self, simhash: str) -> bool:
        """Quick check: does a near-duplicate already exist in the index?"""
        return len(self.find_duplicates(simhash)) > 0

    def __len__(self) -> int:
        return len(self._hashes)
