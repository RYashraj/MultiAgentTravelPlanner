"""ChromaDB Vector Store module."""
import logging
from typing import Any
import chromadb
from chromadb.config import Settings

from app.core.config import get_settings

logger = logging.getLogger(__name__)

class ChromaMemoryStore:
    """Vector store manager that uses ChromaDB."""

    def __init__(self, persist_dir: str | None = None, embedding_function: Any = None) -> None:
        self.persist_dir = persist_dir or get_settings().chroma_persist_dir
        self.client = chromadb.PersistentClient(path=self.persist_dir, settings=Settings(anonymized_telemetry=False))
        self.collection = self.client.get_or_create_collection(
            name="voyagerai_memory",
            metadata={"hnsw:space": "cosine"}
        )
        self.embedding_function = embedding_function
        logger.info(f"Initialized ChromaMemoryStore at {self.persist_dir}.")

    def embed_message(self, trip_id: str, message_id: str, role: str, content: str) -> None:
        """Embed and store a message."""
        logger.debug(f"embed_message called for trip {trip_id}, message {message_id}")
        self.collection.add(
            ids=[message_id],
            documents=[content],
            metadatas=[{"trip_id": trip_id, "role": role}]
        )

    def retrieve_context(self, trip_id: str, query: str, k: int = 5) -> list[str]:
        """Retrieve relevant context for a trip based on query."""
        logger.debug(f"retrieve_context called for trip {trip_id}")
        results = self.collection.query(
            query_texts=[query],
            n_results=k,
            where={"trip_id": trip_id}
        )
        if not results or not results["documents"] or not results["documents"][0]:
            return []
        
        return results["documents"][0]
