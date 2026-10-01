"""Configuração da aplicação, lida de variáveis de ambiente (ou do ficheiro .env)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

ROOT = Path(__file__).resolve().parent.parent
if load_dotenv:
    load_dotenv(ROOT / ".env")


def _get(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    index_dir: Path
    templates_dir: Path

    # LLM: "openai_compatible" (Ollama, vLLM, LM Studio, ...) ou "azure_openai"
    llm_provider: str
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_temperature: float
    llm_max_tokens: int
    azure_api_version: str

    # Embeddings: "ollama", "openai_compatible" ou "sentence_transformers"
    embed_provider: str
    embed_model: str
    embed_base_url: str
    embed_api_key: str
    embed_query_prefix: str
    embed_doc_prefix: str
    embed_batch_size: int

    # Pesquisa
    top_k_legislacao: int
    top_k_exemplos: int
    max_context_chars: int

    app_password: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            data_dir=Path(_get("DATA_DIR", str(ROOT / "data"))),
            index_dir=Path(_get("INDEX_DIR", str(ROOT / "index"))),
            templates_dir=Path(_get("TEMPLATES_DIR", str(ROOT / "templates"))),
            llm_provider=_get("LLM_PROVIDER", "openai_compatible"),
            llm_base_url=_get("LLM_BASE_URL", "http://localhost:11434/v1"),
            llm_api_key=_get("LLM_API_KEY", "ollama"),
            llm_model=_get("LLM_MODEL", "qwen2.5:7b"),
            llm_temperature=float(_get("LLM_TEMPERATURE", "0.2")),
            llm_max_tokens=int(_get("LLM_MAX_TOKENS", "2048")),
            azure_api_version=_get("AZURE_API_VERSION", "2024-10-21"),
            embed_provider=_get("EMBED_PROVIDER", "ollama"),
            embed_model=_get("EMBED_MODEL", "bge-m3"),
            embed_base_url=_get("EMBED_BASE_URL", "http://localhost:11434"),
            embed_api_key=_get("EMBED_API_KEY", ""),
            embed_query_prefix=_get("EMBED_QUERY_PREFIX", ""),
            embed_doc_prefix=_get("EMBED_DOC_PREFIX", ""),
            embed_batch_size=int(_get("EMBED_BATCH_SIZE", "32")),
            top_k_legislacao=int(_get("TOP_K_LEGISLACAO", "6")),
            top_k_exemplos=int(_get("TOP_K_EXEMPLOS", "4")),
            max_context_chars=int(_get("MAX_CONTEXT_CHARS", "24000")),
            app_password=_get("APP_PASSWORD", ""),
        )
