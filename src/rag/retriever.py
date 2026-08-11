"""
Loads the index built by ingest.py and answers similarity search queries.
Kept separate from agent.py so it can be unit-tested or swapped
(e.g. for Chroma) without touching the agent logic.
"""

import json
from pathlib import Path

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parent.parent
INDEX_DIR = ROOT / "rag_index"


class Retriever:
    def __init__(self):
        index_path = INDEX_DIR / "index.faiss"
        meta_path = INDEX_DIR / "metadata.json"
        if not index_path.exists() or not meta_path.exists():
            raise FileNotFoundError(
                "No index found. Run `python -m rag.ingest` first."
            )

        self.index = faiss.read_index(str(index_path))
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        self.records = meta["records"]
        self.model = SentenceTransformer(meta["model"])

    def search(self, query: str, top_k: int = 5, source_type: str | None = None):
        """
        Returns a list of {text, source, source_type, score} dicts,
        best match first. If source_type is "doc" or "log", restricts
        the search to that source only.
        """
        query_vec = self.model.encode([query], normalize_embeddings=True)
        query_vec = np.asarray(query_vec, dtype="float32")

        # Over-fetch when filtering by source_type so we still return top_k
        # after filtering.
        fetch_k = top_k * 4 if source_type else top_k
        scores, indices = self.index.search(query_vec, fetch_k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            record = self.records[idx]
            if source_type and record["source_type"] != source_type:
                continue
            results.append(
                {
                    "text": record["text"],
                    "source": record["source"],
                    "source_type": record["source_type"],
                    "score": float(score),
                }
            )
            if len(results) >= top_k:
                break
        return results
