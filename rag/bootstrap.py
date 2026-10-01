"""Indexação automática dos documentos listados em data/publico/manifesto.yaml.

Usada no arranque da aplicação (útil em alojamentos com disco efémero, como o Streamlit
Community Cloud). Só (re)indexa ficheiros novos ou alterados, comparando o hash do conteúdo.

Também pode ser corrida manualmente:  python -m rag.bootstrap
"""
from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import yaml

from .ingest import ingerir
from .store import Store

CAMPOS_META = ("fonte", "diploma", "tipo_peca", "tipo_procedimento", "tipo_contrato", "ano", "titulo_doc")


@dataclass
class Resultado:
    ficheiro: str
    estado: str  # indexado | atual | erro
    detalhe: str = ""


def ler_manifesto(pasta: Path) -> List[Dict[str, str]]:
    f = pasta / "manifesto.yaml"
    if not f.exists():
        return []
    return yaml.safe_load(f.read_text(encoding="utf-8")) or []


def indexar_manifesto(store: Store, pasta: Path) -> List[Resultado]:
    entradas = ler_manifesto(pasta)
    hashes = store.hashes_por_fonte()
    resultados: List[Resultado] = []
    for entrada in entradas:
        rel = str(entrada.get("ficheiro", "")).strip()
        caminho = pasta / rel
        if not rel or not caminho.is_file():
            resultados.append(Resultado(rel, "erro", "ficheiro não encontrado"))
            continue
        data = caminho.read_bytes()
        h = hashlib.sha1(data).hexdigest()
        source = f"publico/{rel}"
        if hashes.get(source) == h:
            resultados.append(Resultado(rel, "atual"))
            continue
        meta = {k: str(entrada[k]) for k in CAMPOS_META if entrada.get(k)}
        meta["hash"] = h
        try:
            n = ingerir(store, caminho.name, data, meta, source=source)
            resultados.append(Resultado(rel, "indexado", f"{n} excertos"))
        except Exception as e:  # noqa: BLE001 - continuar com os restantes
            resultados.append(Resultado(rel, "erro", str(e)))
    return resultados


def main() -> int:
    from .config import Settings
    from .embeddings import Embedder

    settings = Settings.from_env()
    store = Store(settings.index_dir, Embedder(settings))
    for r in indexar_manifesto(store, settings.data_dir / "publico"):
        print(f"[{r.estado}] {r.ficheiro} {r.detalhe}")
    print(f"Total no índice: {store.contar()} excertos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
