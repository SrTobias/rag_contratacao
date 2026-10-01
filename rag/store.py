"""Índice local: Chroma (vetores) + BM25 (palavras-chave), combinados por Reciprocal Rank Fusion.

A pesquisa por palavras-chave é essencial neste domínio: referências como
"artigo 70.º", códigos CPV ou termos técnicos exatos são mal servidas só por embeddings.
"""
from __future__ import annotations

import hashlib
import re
import sys
import threading
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .chunking import Chunk
from .embeddings import Embedder

COLLECTION = "contratacao"
RRF_K = 60

_STOPWORDS = set(
    "a ao aos as com da das de do dos e em na nas no nos o os ou para pela pelas pelo pelos por "
    "que se sem sua suas seu seus um uma umas uns à às é".split()
)

Filtros = Dict[str, Any]


@dataclass
class Hit:
    id: str
    text: str
    metadata: Dict[str, str]
    score: float = 0.0

    @property
    def referencia(self) -> str:
        m = self.metadata
        if m.get("fonte") == "legislacao" and m.get("artigo"):
            return f"{m.get('diploma', '')}, {m.get('seccao', '')}"
        return f"{m.get('titulo_doc') or m.get('source', '')}" + (f" — {m['seccao']}" if m.get("seccao") else "")


def tokenizar(text: str) -> List[str]:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return [t for t in re.findall(r"\w+", text) if t not in _STOPWORDS]


def _where(filtros: Optional[Filtros]) -> Optional[dict]:
    clausulas = []
    for k, v in (filtros or {}).items():
        if v is None:
            continue
        if isinstance(v, (list, tuple, set)):
            clausulas.append({k: {"$in": list(v)}})
        else:
            clausulas.append({k: v})
    if not clausulas:
        return None
    return clausulas[0] if len(clausulas) == 1 else {"$and": clausulas}


def _corresponde(meta: Dict[str, str], filtros: Optional[Filtros]) -> bool:
    for k, v in (filtros or {}).items():
        if v is None:
            continue
        if isinstance(v, (list, tuple, set)):
            if meta.get(k) not in v:
                return False
        elif meta.get(k) != v:
            return False
    return True


def _sqlite_recente() -> None:
    """O Chroma exige SQLite >= 3.35; em Linux com SQLite antigo usa-se o pysqlite3-binary."""
    try:
        import pysqlite3  # noqa: F401
    except ImportError:
        return
    sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")


def _limpar_meta(meta: Dict[str, Any]) -> Dict[str, Any]:
    return {k: (v if isinstance(v, (str, int, float, bool)) else str(v)) for k, v in meta.items() if v is not None}


class Store:
    def __init__(self, index_dir: Path, embedder: Embedder):
        _sqlite_recente()
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        index_dir.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=str(index_dir / "chroma"), settings=ChromaSettings(anonymized_telemetry=False)
        )
        self.col = self.client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})
        self.embedder = embedder
        self._lock = threading.Lock()
        self._bm25 = None
        self._bm25_ids: List[str] = []
        self._bm25_docs: List[str] = []
        self._bm25_metas: List[Dict[str, str]] = []

    # ------------------------------------------------------------------ escrita

    def adicionar(self, chunks: List[Chunk], source: str) -> int:
        """Indexa os excertos de um documento, substituindo versões anteriores do mesmo `source`."""
        self.remover(source)
        if not chunks:
            return 0
        textos = [c.text for c in chunks]
        embeddings = self.embedder.embed_documents(textos)
        ids = [hashlib.sha1(f"{source}|{i}|{c.text}".encode()).hexdigest() for i, c in enumerate(chunks)]
        metas = [_limpar_meta({**c.metadata, "source": source}) for c in chunks]
        for i in range(0, len(ids), 500):
            self.col.add(
                ids=ids[i : i + 500],
                documents=textos[i : i + 500],
                metadatas=metas[i : i + 500],
                embeddings=embeddings[i : i + 500],
            )
        self._invalidar()
        return len(chunks)

    def remover(self, source: str) -> None:
        self.col.delete(where={"source": source})
        self._invalidar()

    def _invalidar(self) -> None:
        with self._lock:
            self._bm25 = None

    # ------------------------------------------------------------------ leitura

    def contar(self) -> int:
        return self.col.count()

    def listar_fontes(self) -> List[Dict[str, Any]]:
        res = self.col.get(include=["metadatas"])
        agregado: Dict[str, Dict[str, Any]] = {}
        for meta in res["metadatas"]:
            src = meta.get("source", "?")
            if src not in agregado:
                agregado[src] = {
                    "source": src,
                    "fonte": meta.get("fonte", ""),
                    "diploma": meta.get("diploma", ""),
                    "tipo_peca": meta.get("tipo_peca", ""),
                    "tipo_procedimento": meta.get("tipo_procedimento", ""),
                    "tipo_contrato": meta.get("tipo_contrato", ""),
                    "excertos": 0,
                }
            agregado[src]["excertos"] += 1
        return sorted(agregado.values(), key=lambda d: (d["fonte"], d["source"]))

    def hashes_por_fonte(self) -> Dict[str, str]:
        """source -> hash do ficheiro de origem (para documentos indexados com hash)."""
        res = self.col.get(where={"hash": {"$ne": ""}}, include=["metadatas"])
        return {m["source"]: m["hash"] for m in res["metadatas"] if m.get("hash")}

    def obter_artigos(self, artigos: List[str], filtros: Optional[Filtros] = None) -> List[Hit]:
        """Obtém diretamente artigos pelo número (ex.: ['70', '46-A']), sem pesquisa semântica."""
        if not artigos:
            return []
        res = self.col.get(
            where=_where({**(filtros or {}), "fonte": "legislacao", "artigo": list(artigos)}),
            include=["documents", "metadatas"],
        )
        hits = [Hit(i, d, m, 1.0) for i, d, m in zip(res["ids"], res["documents"], res["metadatas"])]
        ordem = {a: n for n, a in enumerate(artigos)}
        return sorted(hits, key=lambda h: (ordem.get(h.metadata.get("artigo", ""), 999), h.text))

    def pesquisar(self, query: str, k: int = 6, filtros: Optional[Filtros] = None, candidatos: int = 30) -> List[Hit]:
        """Pesquisa híbrida (vetorial + BM25) com fusão RRF."""
        total = self.col.count()
        if total == 0:
            return []
        n = min(candidatos, total)
        res = self.col.query(
            query_embeddings=[self.embedder.embed_query(query)],
            n_results=n,
            where=_where(filtros),
            include=["documents", "metadatas"],
        )
        vetorial = [Hit(i, d, m) for i, d, m in zip(res["ids"][0], res["documents"][0], res["metadatas"][0])]
        lexical = self._bm25_pesquisar(query, n, filtros)

        scores: Dict[str, float] = defaultdict(float)
        por_id: Dict[str, Hit] = {}
        for lista in (vetorial, lexical):
            for rank, hit in enumerate(lista):
                scores[hit.id] += 1.0 / (RRF_K + rank + 1)
                por_id.setdefault(hit.id, hit)
        ordenados = sorted(scores, key=scores.get, reverse=True)[:k]
        return [Hit(i, por_id[i].text, por_id[i].metadata, scores[i]) for i in ordenados]

    def _bm25_pesquisar(self, query: str, n: int, filtros: Optional[Filtros]) -> List[Hit]:
        from rank_bm25 import BM25Okapi

        with self._lock:
            if self._bm25 is None:
                res = self.col.get(include=["documents", "metadatas"])
                self._bm25_ids, self._bm25_docs, self._bm25_metas = res["ids"], res["documents"], res["metadatas"]
                self._bm25 = BM25Okapi([tokenizar(d) for d in self._bm25_docs]) if self._bm25_docs else None
            bm25 = self._bm25
        if bm25 is None:
            return []
        scores = bm25.get_scores(tokenizar(query))
        idx = [i for i in range(len(scores)) if scores[i] > 0 and _corresponde(self._bm25_metas[i], filtros)]
        idx.sort(key=lambda i: scores[i], reverse=True)
        return [Hit(self._bm25_ids[i], self._bm25_docs[i], self._bm25_metas[i], float(scores[i])) for i in idx[:n]]
