import pytest

pytest.importorskip("chromadb")

from rag.bootstrap import indexar_manifesto  # noqa: E402
from rag.config import ROOT  # noqa: E402
from rag.store import Store  # noqa: E402
from tests.test_chunking import CCP  # noqa: E402
from tests.test_store import FakeEmbedder  # noqa: E402


def test_manifesto_indexa_so_novos_ou_alterados(tmp_path):
    pasta = tmp_path / "publico"
    (pasta / "legislacao").mkdir(parents=True)
    (pasta / "legislacao" / "ccp.txt").write_text(CCP, encoding="utf-8")
    (pasta / "manifesto.yaml").write_text(
        "- {ficheiro: legislacao/ccp.txt, fonte: legislacao, diploma: CCP}\n"
        "- {ficheiro: legislacao/falta.pdf, fonte: legislacao, diploma: CCP}\n",
        encoding="utf-8",
    )
    store = Store(tmp_path / "index", FakeEmbedder())

    r1 = indexar_manifesto(store, pasta)
    assert [r.estado for r in r1] == ["indexado", "erro"]
    assert store.obter_artigos(["67"], {"diploma": "CCP"})

    r2 = indexar_manifesto(store, pasta)
    assert r2[0].estado == "atual"

    (pasta / "legislacao" / "ccp.txt").write_text(CCP + "\nArtigo 68.º\nFuncionamento\n1 - Texto.\n", encoding="utf-8")
    r3 = indexar_manifesto(store, pasta)
    assert r3[0].estado == "indexado"
    assert store.obter_artigos(["68"], {"diploma": "CCP"})


def test_manifesto_do_repositorio_e_valido():
    from rag.bootstrap import ler_manifesto

    assert isinstance(ler_manifesto(ROOT / "data" / "publico"), list)
