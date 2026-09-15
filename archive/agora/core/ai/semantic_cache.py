import numpy as np
import faiss
import pickle
from pathlib import Path
from sentence_transformers import SentenceTransformer

class SemanticCache:
    def __init__(self, model_name: str = 'all-MiniLM-L6-v2', cache_dir: Path = Path("./cache")):
        self.model = SentenceTransformer(model_name)
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = cache_dir / "index.faiss"
        self.metadata_path = cache_dir / "metadata.pkl"
        self._load_or_create_index()

    def _load_or_create_index(self):
        if self.index_path.exists() and self.metadata_path.exists():
            self.index = faiss.read_index(str(self.index_path))
            with open(self.metadata_path, 'rb') as f:
                self.metadata = pickle.load(f)
        else:
            self.index = faiss.IndexFlatL2(384)  # MiniLM-L6-v2 dimension
            self.metadata = []

    def search(self, query: str, threshold: float = 0.8):
        query_vec = self.model.encode([query])
        distances, indices = self.index.search(query_vec, 1)
        if len(indices[0]) > 0 and distances[0][0] < threshold:
            return self.metadata[indices[0][0]]
        return None

    def add(self, text: str, data):
        vec = self.model.encode([text])
        self.index.add(vec)
        self.metadata.append(data)
        faiss.write_index(self.index, str(self.index_path))
        with open(self.metadata_path, 'wb') as f:
            pickle.dump(self.metadata, f)
