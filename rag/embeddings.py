"""Embeddings locais (Ollama ou sentence-transformers) ou via servidor OpenAI-compatível."""
from __future__ import annotations

from typing import List

import requests

from .config import Settings

BATCH_SIZE = 32


class Embedder:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.provider = settings.embed_provider
        self._st_model = None
        self._client = None
        if self.provider == "openai_compatible":
            from openai import OpenAI

            self._client = OpenAI(base_url=settings.embed_base_url, api_key=settings.embed_api_key or "none")
        elif self.provider not in ("ollama", "sentence_transformers"):
            raise ValueError(f"EMBED_PROVIDER desconhecido: {self.provider}")

    def _embed(self, texts: List[str]) -> List[List[float]]:
        if self.provider == "ollama":
            resp = requests.post(
                f"{self.settings.embed_base_url.rstrip('/')}/api/embed",
                json={"model": self.settings.embed_model, "input": texts},
                timeout=600,
            )
            resp.raise_for_status()
            return resp.json()["embeddings"]
        if self.provider == "openai_compatible":
            resp = self._client.embeddings.create(model=self.settings.embed_model, input=texts)
            return [d.embedding for d in resp.data]
        if self._st_model is None:
            from sentence_transformers import SentenceTransformer

            self._st_model = SentenceTransformer(self.settings.embed_model)
        return self._st_model.encode(texts, normalize_embeddings=True).tolist()

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        prefix = self.settings.embed_doc_prefix
        out: List[List[float]] = []
        for i in range(0, len(texts), BATCH_SIZE):
            out.extend(self._embed([prefix + t for t in texts[i : i + BATCH_SIZE]]))
        return out

    def embed_query(self, text: str) -> List[float]:
        return self._embed([self.settings.embed_query_prefix + text])[0]
