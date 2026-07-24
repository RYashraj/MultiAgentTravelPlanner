"""ChromaDB Vector Store module for Travel Planner memory."""
import logging
from typing import Any

import chromadb
from chromadb.api import ClientAPI
from chromadb.api.types import EmbeddingFunction, Documents, Embeddings

from app.core.config import get_settings

class GeminiEmbeddingFunction(EmbeddingFunction):
    def __init__(self, api_key: str):
        self.api_key = api_key
    
    def __call__(self, input: Documents) -> Embeddings:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        embeddings_model = GoogleGenerativeAIEmbeddings(
            model="models/embedding-001", 
            google_api_key=self.api_key
        )
        return embeddings_model.embed_documents(input)

logger = logging.getLogger(__name__)


class ChromaMemoryStore:
    """Vector store manager using ChromaDB PersistentClient for per-trip message memory."""

    def __init__(self, persist_dir: str | None = None, embedding_function: Any = None) -> None:
        self.persist_dir = persist_dir or get_settings().chroma_persist_dir
        self.client: ClientAPI = chromadb.PersistentClient(path=self.persist_dir)
        
        if embedding_function is None:
            api_key = get_settings().gemini_api_key
            if api_key:
                self._embedding_function = GeminiEmbeddingFunction(api_key=api_key)
            else:
                self._embedding_function = None
        else:
            self._embedding_function = embedding_function

    def _get_embedding_function(self) -> Any:
        """Internal method returning embedding function. Easy to swap in custom embedding backends later."""
        return self._embedding_function

    def _get_collection_name(self, trip_id: str) -> str:
        """Derives a valid Chroma collection name from a trip_id.

        Chroma collection names must be 3-63 characters, start/end with alphanumeric,
        and contain only alphanumeric, underscores, or hyphens.
        """
        sanitized = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in trip_id)
        if not (sanitized.startswith("trip_") or sanitized.startswith("trip-")):
            sanitized = f"trip_{sanitized}"
        sanitized = sanitized.replace("-", "_")
        name = sanitized[:63].rstrip("_-")
        if len(name) < 3:
            name = f"trip_{name}"
        return name

    def _get_or_create_collection(self, trip_id: str) -> Any:
        col_name = self._get_collection_name(trip_id)
        emb_fn = self._get_embedding_function()
        if emb_fn is not None:
            return self.client.get_or_create_collection(name=col_name, embedding_function=emb_fn)
        return self.client.get_or_create_collection(name=col_name)

    def embed_message(self, trip_id: str, message_id: str, role: str, content: str) -> None:
        """Embeds and upserts a message into the trip's vector collection."""
        try:
            collection = self._get_or_create_collection(trip_id)
            doc_text = f"{role}: {content}"
            collection.upsert(
                ids=[message_id],
                documents=[doc_text],
                metadatas=[{"role": role, "message_id": message_id, "trip_id": trip_id, "content": content}],
            )
        except Exception as exc:
            logger.error("Failed to embed message %s for trip %s: %s", message_id, trip_id, exc, exc_info=True)
            raise

    def retrieve_context(self, trip_id: str, query: str, k: int = 5) -> list[str]:
        """Retrieves top-k relevant message contexts for a trip.

        Returns [] gracefully if collection is empty or missing without raising errors.
        """
        try:
            col_name = self._get_collection_name(trip_id)
            existing_collections = [c.name for c in self.client.list_collections()]
            if col_name not in existing_collections:
                return []

            emb_fn = self._get_embedding_function()
            if emb_fn is not None:
                collection = self.client.get_collection(name=col_name, embedding_function=emb_fn)
            else:
                collection = self.client.get_collection(name=col_name)

            count = collection.count()
            if count == 0:
                return []

            n_results = min(k, count)
            results = collection.query(
                query_texts=[query],
                n_results=n_results,
            )

            if results and "documents" in results and results["documents"]:
                docs = results["documents"][0]
                return list(docs) if docs is not None else []
            return []
        except Exception as exc:
            logger.warning("Error retrieving memory context for trip %s: %s", trip_id, exc)
            return []
