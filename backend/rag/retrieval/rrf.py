"""
Reciprocal Rank Fusion (RRF) for combining results from multiple queries.
"""
from typing import Dict, List

from config import settings


def reciprocal_rank_fusion(
    results_per_query: Dict[str, List[str]],
    k: int = None,
) -> List[str]:
    """
    Combine ranked results from multiple queries using RRF.
    
    For each chunk across all query result lists:
        score += 1 / (k + rank)
    
    Args:
        results_per_query: Dict mapping query → ordered list of chunk_ids
        k: RRF constant (default from settings.RRF_K = 60)
        
    Returns:
        List of chunk_ids sorted by fused score (descending)
    """
    if k is None:
        k = settings.RRF_K

    fused_scores: Dict[str, float] = {}

    for _query, chunk_ids in results_per_query.items():
        for rank, chunk_id in enumerate(chunk_ids, start=1):
            fused_scores[chunk_id] = fused_scores.get(chunk_id, 0.0) + 1.0 / (k + rank)

    # Sort by fused score descending
    sorted_chunks = sorted(fused_scores.keys(), key=lambda cid: fused_scores[cid], reverse=True)

    return sorted_chunks
