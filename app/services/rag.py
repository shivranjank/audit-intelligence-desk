import re
from pathlib import Path

import faiss
import numpy as np
import yaml
from loguru import logger
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

from app.models.schemas import PolicyChunk

POLICIES_DIR = Path("data/policies")
APP_CONFIG_PATH = Path("config/app_config.yaml")
_RAG_CONFIG = yaml.safe_load(APP_CONFIG_PATH.read_text(encoding="utf-8"))["rag"]

SEMANTIC_CHUNK_THRESHOLD = _RAG_CONFIG["semantic_chunk_threshold"]
EMBED_MODEL_NAME = _RAG_CONFIG["embed_model"]
DEFAULT_RETRIEVE_K = _RAG_CONFIG["retrieve_k"]
DEFAULT_RRF_K = _RAG_CONFIG["rrf_k"]
DEFAULT_FETCH_N = _RAG_CONFIG["fetch_n"]
DEFAULT_MMR_LAMBDA = _RAG_CONFIG["mmr_lambda"]

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _parse_policy_file(path: Path) -> tuple[dict, str]:
    raw = path.read_text(encoding="utf-8")
    if raw.startswith("---"):
        _, frontmatter, body = raw.split("---", 2)
        meta = yaml.safe_load(frontmatter) or {}
    else:
        meta, body = {}, raw
    return meta, body.strip()


def load_policy_chunk(path: Path) -> PolicyChunk:
    """Parse a single policy-shaped markdown file into one unchunked PolicyChunk.

    Used to load redteam fixtures (e.g. the injection fixture) for deliberate,
    guaranteed-exposure testing rather than relying on retrieval ranking.
    """
    meta, body = _parse_policy_file(path)
    return PolicyChunk(
        policy_ref=meta.get("policy_ref", path.stem),
        title=meta.get("title", path.stem),
        anomaly_type=meta.get("anomaly_type"),
        text=body,
    )


def _semantic_chunk(text: str, model: SentenceTransformer) -> list[str]:
    """Split text into sentences, group consecutive sentences into a chunk while
    cos(sentence[n], sentence[n+1]) stays above SEMANTIC_CHUNK_THRESHOLD, split otherwise."""
    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
    if len(sentences) <= 1:
        return sentences

    embeddings = model.encode([f"search_document: {s}" for s in sentences], normalize_embeddings=True)
    chunks: list[str] = []
    current = [sentences[0]]
    for i in range(1, len(sentences)):
        similarity = float(np.dot(embeddings[i - 1], embeddings[i]))
        if similarity >= SEMANTIC_CHUNK_THRESHOLD:
            current.append(sentences[i])
        else:
            chunks.append(" ".join(current))
            current = [sentences[i]]
    chunks.append(" ".join(current))
    return chunks


class PolicyRAG:
    """Hybrid RAG over the internal policy corpus: dense (FAISS) + sparse (BM25),
    fused with Reciprocal Rank Fusion, diversified with MMR."""

    def __init__(self, model_name: str = EMBED_MODEL_NAME) -> None:
        self._model = SentenceTransformer(model_name, trust_remote_code=True)
        self._chunks: list[PolicyChunk] = []
        self._embeddings: np.ndarray | None = None
        self._index: faiss.Index | None = None
        self._bm25: BM25Okapi | None = None

    def build_index(self, policy_paths: list[Path] | None = None) -> None:
        paths = policy_paths if policy_paths is not None else sorted(POLICIES_DIR.glob("*.md"))
        logger.debug(f"ACTION: build_index | input=paths={[p.name for p in paths]}")

        chunks: list[PolicyChunk] = []
        for path in paths:
            meta, body = _parse_policy_file(path)
            for chunk_text in _semantic_chunk(body, self._model):
                chunks.append(
                    PolicyChunk(
                        policy_ref=meta.get("policy_ref", path.stem),
                        title=meta.get("title", path.stem),
                        anomaly_type=meta.get("anomaly_type"),
                        text=chunk_text,
                    )
                )

        if not chunks:
            raise ValueError(f"No policy chunks found under {paths}")

        self._chunks = chunks
        corpus_texts = [f"search_document: {c.text}" for c in chunks]
        embeddings = self._model.encode(corpus_texts, normalize_embeddings=True)
        self._embeddings = np.asarray(embeddings, dtype="float32")

        index = faiss.IndexFlatIP(self._embeddings.shape[1])
        index.add(self._embeddings)
        self._index = index

        tokenized_corpus = [c.text.lower().split() for c in chunks]
        self._bm25 = BM25Okapi(tokenized_corpus)

        logger.success(f"ACTION: build_index | output=chunks={len(chunks)}")

    def retrieve(
        self,
        query: str,
        k: int = DEFAULT_RETRIEVE_K,
        rrf_k: int = DEFAULT_RRF_K,
        fetch_n: int = DEFAULT_FETCH_N,
    ) -> list[PolicyChunk]:
        if self._index is None or self._bm25 is None or self._embeddings is None:
            raise RuntimeError("Index not built. Call build_index() first.")

        n = min(fetch_n, len(self._chunks))

        query_embedding = np.asarray(
            self._model.encode([f"search_query: {query}"], normalize_embeddings=True), dtype="float32"
        )
        _, dense_indices = self._index.search(query_embedding, n)
        dense_rank = [int(i) for i in dense_indices[0] if i != -1]

        bm25_scores = self._bm25.get_scores(query.lower().split())
        sparse_rank = list(np.argsort(bm25_scores)[::-1][:n])

        rrf_scores: dict[int, float] = {}
        for rank_list in (dense_rank, sparse_rank):
            for rank, idx in enumerate(rank_list):
                rrf_scores[idx] = rrf_scores.get(idx, 0.0) + 1.0 / (rrf_k + rank + 1)
        fused = sorted(rrf_scores.items(), key=lambda kv: kv[1], reverse=True)
        candidate_indices = [idx for idx, _ in fused[:n]]

        selected = self._mmr(query_embedding[0], candidate_indices, k=min(k, len(candidate_indices)))
        return [self._chunks[i] for i in selected]

    def _mmr(
        self, query_vec: np.ndarray, candidate_indices: list[int], k: int, lambda_mult: float = DEFAULT_MMR_LAMBDA
    ) -> list[int]:
        if not candidate_indices:
            return []
        remaining = list(candidate_indices)
        selected: list[int] = []

        while remaining and len(selected) < k:
            best_idx, best_score = None, float("-inf")
            for idx in remaining:
                relevance = float(np.dot(query_vec, self._embeddings[idx]))
                diversity = (
                    max(float(np.dot(self._embeddings[idx], self._embeddings[s])) for s in selected)
                    if selected
                    else 0.0
                )
                score = lambda_mult * relevance - (1 - lambda_mult) * diversity
                if score > best_score:
                    best_idx, best_score = idx, score
            selected.append(best_idx)
            remaining.remove(best_idx)

        return selected
