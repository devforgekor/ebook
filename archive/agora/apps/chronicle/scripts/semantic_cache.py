import numpy as np
import faiss
import json
import logging
import pickle
from pathlib import Path
from sentence_transformers import SentenceTransformer
from datetime import datetime

logger = logging.getLogger(__name__)

class SemanticCache:
    def __init__(
        self, 
        model_name: str = 'all-MiniLM-L6-v2', 
        index_path: str = 'chat_backup/state/semantic_cache.index',
        store_path: str = 'chat_backup/state/semantic_cache_store.pkl'
    ):
        self.model = SentenceTransformer(model_name)
        self.index_path = Path(index_path)
        self.store_path = Path(store_path)
        self.dimension = 384  # MiniLM-L6-v2 dimension
        
        self.index = faiss.IndexFlatL2(self.dimension)
        self.cache_store = []  # List of (user_message, assistant_response, metadata)
        
        self.load()

    def add(self, user_message: str, assistant_response: str, metadata: dict = None):
        if not user_message or not assistant_response:
            return
            
        embedding = self.model.encode([user_message], normalize_embeddings=True).astype('float32')
        self.index.add(embedding)
        self.cache_store.append({
            "user": user_message,
            "assistant": assistant_response,
            "metadata": metadata or {},
            "timestamp": datetime.now().isoformat()
        })
        
    def query(self, user_message: str, threshold: float = 0.5):
        """
        Query the cache for a similar user message.
        L2 distance: smaller is more similar. 
        For MiniLM-L6-v2 (normalized), 0.5 is a reasonably strict threshold.
        """
        if self.index.ntotal == 0:
            return None
            
        embedding = self.model.encode([user_message], normalize_embeddings=True).astype('float32')
        distances, indices = self.index.search(embedding, 1)
        
        if distances[0][0] < threshold:
            idx = indices[0][0]
            if idx < len(self.cache_store):
                return self.cache_store[idx]
        return None

    def save(self):
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(self.index_path))
        with open(self.store_path, 'wb') as f:
            pickle.dump(self.cache_store, f)
        logger.info(f"Saved semantic cache with {len(self.cache_store)} items.")

    def load(self):
        if self.index_path.exists() and self.store_path.exists():
            try:
                self.index = faiss.read_index(str(self.index_path))
                with open(self.store_path, 'rb') as f:
                    self.cache_store = pickle.load(f)
                logger.info(f"Loaded semantic cache with {len(self.cache_store)} items.")
            except Exception as e:
                logger.error(f"Failed to load cache: {e}")
                self.index = faiss.IndexFlatL2(self.dimension)
                self.cache_store = []
