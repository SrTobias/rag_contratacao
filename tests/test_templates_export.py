import io

from docx import Document

from rag.config import ROOT
from rag.export_docx import exportar_docx
from rag.templates import carregar_templates, rotulo, template_personalizado


def test_templates_carregam():
    templates = carregar_templates(ROOT / "templates")
    assert {"decisao_contratar", "programa_procedimento", "convite", "caderno_encargos",
            "relatorio_preliminar", "relatorio_final", "minuta_contrato"} <= set(templates)
    for t in templates.values():
        assert t.secoes, t.id
        assert len({s.id for s in t.secoes}) == len(t.secoes), f"ids duplicados em {t.id}"
        assert t.numeracao in ("artigo", "clausula", "seccao")
        for s in t.secoes:
            assert all(isinstance(a, str) for a in s.base_legal)


def test_condicoes_por_tipo_de_contrato():
    ce = carregar_templates(ROOT / "templates")["caderno_encargos"]
    obras = {s.id for s in ce.secoes_aplicaveis("concurso_publico", "empreitada")}
    bens = {s.id for s in ce.secoes_aplicaveis("concurso_publico", "aquisicao_bens")}
    assert "consignacao" in obras and "consignacao" not in bens
    assert "entrega" in bens and "entrega" not in obras


def test_rotulos_e_peca_livre():
    assert rotulo("artigo", 3) == "Artigo 3.º"
    assert rotulo("clausula", 3) == "Cláusula 3.ª"
    t = template_personalizado("Resposta a esclarecimentos", ["Enquadramento", "", "Respostas"])
    assert [s.titulo for s in t.secoes] == ["Enquadramento", "Respostas"]


def test_exportar_docx():
    data = exportar_docx(
        "Caderno de Encargos",
        "Aquisição de serviços",
        "clausula",
        [
            {"rotulo": "Cláusula 1.ª", "titulo": "Objeto", "parte": "PARTE I", "texto": "1 - O **objeto** é [PREENCHER: objeto].\n- item"},
            {"rotulo": "Cláusula 2.ª", "titulo": "Prazo", "parte": "PARTE I", "texto": "Prazo de 12 meses."},
        ],
        ["CCP, Artigo 42.º"],
    )
    doc = Document(io.BytesIO(data))
    texto = "\n".join(p.text for p in doc.paragraphs)
    assert "Cláusula 1.ª" in texto and "[PREENCHER: objeto]" in texto and "CCP, Artigo 42.º" in texto
    assert texto.count("PARTE I") == 1
