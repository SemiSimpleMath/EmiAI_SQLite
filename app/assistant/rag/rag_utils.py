# rag_utils.py
import re

from app.models.base import get_session
from app.assistant.database.db_handler import RAGDatabase

from app.assistant.utils.logging_config import get_logger
logger = get_logger(__name__)

# Lazy loading for optional dependencies (not available in alpha)
_nlp = None
_embedding_model = None
_numpy = None

def _get_nlp():
    """Lazy load spaCy model"""
    global _nlp
    if _nlp is None:
        try:
            import spacy
            _nlp = spacy.load("en_core_web_sm")
        except ImportError:
            logger.warning("spaCy not available - RAG features disabled")
            raise ImportError("spaCy not installed. RAG features require spaCy.")
    return _nlp

def _get_embedding_model():
    """Lazy load embedding model"""
    global _embedding_model
    if _embedding_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        except ImportError:
            logger.warning("sentence-transformers not available - RAG features disabled")
            raise ImportError("sentence-transformers not installed. RAG features require sentence-transformers.")
    return _embedding_model

def _get_numpy():
    """Lazy load numpy"""
    global _numpy
    if _numpy is None:
        import numpy as np
        _numpy = np
    return _numpy


# ---------------------------------------------------------
# ✅ Semantic Search in RAGDatabase (Vector Retrieval)
# ---------------------------------------------------------

def strip_speaker_prefix(text):
    # Matches lines like "Jukka: hey" or "Emi (bot): hello"
    match = re.match(r"^\s*([\w\s]+?)(?:\s*\(.*?\))?:\s+(.*)", text)
    if match:
        speaker, message = match.groups()
        if len(speaker.split()) <= 3:  # simple sanity check
            return message.strip()
    return text.strip()

def query_rag_database(query_text, scopes=None, top_k=3, threshold=0.35, chunk_size=1):
    """
    Query RAG database with semantic search using chunked processing for better performance.
    Requires spacy and sentence-transformers.
    """
    # Get lazy-loaded dependencies
    nlp = _get_nlp()
    embedding_model = _get_embedding_model()
    np = _get_numpy()
    
    doc = nlp(query_text)
    sentences = [sent.text.strip() for sent in doc.sents]
    merged_results = {}

    session = get_session()
    try:
        if not scopes:
            scopes = []

        results = (
            session.query(RAGDatabase)
                .filter(RAGDatabase.scope.in_(scopes))
                .all()
        )

        if not results:
            logger.info(f"No RAG results found for scopes: {scopes}")
            return []

        for i in range(0, len(sentences), chunk_size):
            chunk = " ".join(sentences[i:i + chunk_size])
            query_embedding = np.array(embedding_model.encode(chunk))
            query_norm = np.linalg.norm(query_embedding)

            for result in results:
                stored_embedding = np.array(result.embedding)
                similarity = np.dot(query_embedding, stored_embedding) / (query_norm * np.linalg.norm(stored_embedding))

                if similarity >= threshold:
                    key = (result.document, result.source, result.scope)
                    if key not in merged_results or merged_results[key]["similarity"] < similarity:
                        merged_results[key] = {
                            "document": result.document,
                            "source": result.source,
                            "scope": result.scope,
                            "similarity": similarity,
                            "timestamp": result.timestamp
                        }

        return sorted(merged_results.values(), key=lambda x: x["similarity"], reverse=True)[:top_k]

    except Exception as e:
        logger.error(f"[ERROR] Failed during chunked RAG query: {e}")
        return []
    finally:
        session.close()


def _query_rag_database(query_text, scopes=None, top_k=3, relevance_threshold=0.5):
    """Query RAG database. Requires sentence-transformers."""
    # Get lazy-loaded dependencies
    embedding_model = _get_embedding_model()
    np = _get_numpy()
    
    session = get_session()
    try:
        if not scopes:
            scopes = []

        # ✅ Only fetch entries in scope
        results = (
            session.query(RAGDatabase)
                .filter(RAGDatabase.scope.in_(scopes))
                .all()
        )

        if not results:
            logger.info(f"No RAG results found for scopes: {scopes}")
            return []

        # Embed once
        query_embedding = np.array(embedding_model.encode(query_text))
        query_norm = np.linalg.norm(query_embedding)

        similarities = []
        for result in results:
            stored_embedding = np.array(result.embedding)
            similarity = np.dot(query_embedding, stored_embedding) / (query_norm * np.linalg.norm(stored_embedding))
            if similarity >= relevance_threshold:
                similarities.append({
                    "document": result.document,
                    "source": result.source,
                    "scope": result.scope,
                    "similarity": similarity,
                    "timestamp": result.timestamp
                })

        return sorted(similarities, key=lambda x: x["similarity"], reverse=True)[:top_k]

    except Exception as e:
        logger.error(f"[ERROR] Failed to query RAGDatabase: {e}")
        return []
    finally:
        session.close()


if __name__ == "__main__":
    test_queries = [
        """i work at""",
    ]

    scopes = ["chat", "slack"]  # Adjust to match what your RAGDatabase uses
    top_k = 10
    threshold = 0.45

    for query in test_queries:
        print("=" * 80)
        print(f"Query: {query}")
        results = query_rag_database(query, scopes=scopes, top_k=top_k, threshold=threshold, chunk_size=2)

        if not results:
            print("No relevant results found.")
        else:
            for i, res in enumerate(results, start=1):
                print(f"\nResult #{i}")
                print(f"Similarity: {res['similarity']:.3f}")
                print(f"Source: {res['source']}")
                print(f"Scope: {res['scope']}")
                print(f"Timestamp: {res['timestamp']}")
                print(f"Document:\n{res['document']}")

