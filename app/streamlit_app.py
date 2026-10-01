"""Interface web: geração de peças, consulta e gestão da base documental."""
from __future__ import annotations

import hmac
import sys
from pathlib import Path
from typing import Dict, List

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.config import Settings  # noqa: E402
from rag.embeddings import Embedder  # noqa: E402
from rag.export_docx import exportar_docx  # noqa: E402
from rag.generation import consultar, redigir_secao  # noqa: E402
from rag.ingest import ingerir  # noqa: E402
from rag.llm import LLM  # noqa: E402
from rag.store import Store  # noqa: E402
from rag.taxonomy import CAMPOS_COMUNS, FONTES, TIPOS_CONTRATO, TIPOS_PROCEDIMENTO  # noqa: E402
from rag.templates import Template, carregar_templates, rotulo, template_personalizado  # noqa: E402

st.set_page_config(page_title="Peças de Contratação Pública", page_icon="📄", layout="wide")

PECA_LIVRE = "peca_livre"
NUMERACOES = {"seccao": "1., 2., ...", "artigo": "Artigo 1.º", "clausula": "Cláusula 1.ª"}


@st.cache_resource
def servicos():
    settings = Settings.from_env()
    store = Store(settings.index_dir, Embedder(settings))
    return settings, store, LLM(settings)


settings, store, llm = servicos()
templates = carregar_templates(settings.templates_dir)


def autenticado() -> bool:
    if not settings.app_password or st.session_state.get("auth"):
        return True
    st.title("Peças de Contratação Pública")
    pwd = st.text_input("Palavra-passe", type="password")
    if pwd:
        if hmac.compare_digest(pwd.encode(), settings.app_password.encode()):
            st.session_state.auth = True
            st.rerun()
        st.error("Palavra-passe incorreta.")
    return False


def escrever_stream(stream) -> str:
    """Mostra o texto à medida que é gerado e devolve-o completo."""
    texto = st.write_stream(stream)
    return texto if isinstance(texto, str) else ""


# --------------------------------------------------------------------------- gerar peça

def formulario_dados(template: Template) -> Dict[str, str]:
    dados: Dict[str, str] = {}
    cols = st.columns(2)
    for i, campo in enumerate(CAMPOS_COMUNS + template.campos_extra):
        alvo = cols[i % 2]
        key = f"campo_{campo['id']}"
        if campo.get("tipo") == "textarea":
            dados[campo["id"]] = alvo.text_area(campo["rotulo"], key=key, height=100)
        else:
            dados[campo["id"]] = alvo.text_input(campo["rotulo"], key=key)
    return dados


def pagina_gerar() -> None:
    st.title("Gerar peça de procedimento")
    nomes = {**{k: t.nome for k, t in templates.items()}, PECA_LIVRE: "Outra peça (personalizada)"}
    c1, c2, c3 = st.columns(3)
    tid = c1.selectbox("Peça", list(nomes), format_func=nomes.get, key="g_template")
    proc = c2.selectbox("Procedimento", list(TIPOS_PROCEDIMENTO), format_func=TIPOS_PROCEDIMENTO.get, key="g_proc")
    contrato = c3.selectbox("Tipo de contrato", list(TIPOS_CONTRATO), format_func=TIPOS_CONTRATO.get, key="g_contrato")

    if tid == PECA_LIVRE:
        nome = st.text_input("Nome da peça", key="g_livre_nome")
        numeracao = st.radio("Numeração", list(NUMERACOES), format_func=NUMERACOES.get, horizontal=True, key="g_livre_num")
        titulos = st.text_area("Secções a redigir (uma por linha)", key="g_livre_secoes", height=150)
        template = template_personalizado(nome, titulos.splitlines(), numeracao)
    else:
        template = templates[tid]
        st.caption(template.descricao)
        if template.procedimentos and proc not in template.procedimentos:
            st.warning("Esta peça não é habitual no procedimento selecionado. Confirme a escolha.")

    with st.expander("Dados do procedimento", expanded=True):
        dados = formulario_dados(template)

    aplicaveis = template.secoes_aplicaveis(proc, contrato)
    if tid == PECA_LIVRE:
        secoes = aplicaveis
    else:
        por_id = {s.id: s for s in aplicaveis}
        escolhidas = st.multiselect(
            "Secções a incluir",
            list(por_id),
            default=[s.id for s in aplicaveis if not s.opcional],
            format_func=lambda i: por_id[i].titulo,
            key=f"g_secoes_{tid}_{proc}_{contrato}",
        )
        secoes = [s for s in aplicaveis if s.id in escolhidas]

    if st.button("Gerar peça", type="primary", disabled=not secoes):
        if store.contar() == 0:
            st.warning("O índice está vazio: a peça será gerada sem legislação nem exemplos de suporte.")
        indice = list(enumerate(secoes, 1))
        resultado: List[Dict] = []
        for n, s in indice:
            st.markdown(f"#### {rotulo(template.numeracao, n)} — {s.titulo}")
            try:
                stream, ctx = redigir_secao(llm, store, settings, template, s, n, indice, proc, contrato, dados)
                texto, fontes = escrever_stream(stream), ctx.fontes()
            except Exception as e:  # noqa: BLE001 - mostrar erro e continuar
                st.error(f"Erro ao gerar a secção: {e}")
                texto, fontes = "[PREENCHER: secção não gerada]", []
            resultado.append(
                {"rotulo": rotulo(template.numeracao, n), "titulo": s.titulo, "parte": s.parte, "texto": texto, "fontes": fontes}
            )
        st.session_state.doc = {"template": template, "proc": proc, "contrato": contrato, "indice": indice, "secoes": resultado}
        for i, r in enumerate(resultado):
            st.session_state[f"edit_{i}"] = r["texto"]
        st.rerun()

    if st.session_state.get("doc"):
        editor(st.session_state.doc, dados)


def editor(doc: Dict, dados: Dict[str, str]) -> None:
    template: Template = doc["template"]
    st.divider()
    st.subheader(f"Revisão — {template.nome}")
    st.caption("Edite o texto de cada secção. Os marcadores [PREENCHER] e [VERIFICAR] ficam destacados a amarelo no Word.")

    regen = st.session_state.pop("regen", None)
    if regen is not None:
        n, s = doc["indice"][regen]
        with st.spinner(f"A regenerar «{s.titulo}»..."):
            try:
                stream, ctx = redigir_secao(llm, store, settings, template, s, n, doc["indice"], doc["proc"], doc["contrato"], dados)
                texto = "".join(stream)
                doc["secoes"][regen].update(texto=texto, fontes=ctx.fontes())
                st.session_state[f"edit_{regen}"] = texto
            except Exception as e:  # noqa: BLE001
                st.error(f"Erro ao regenerar: {e}")

    for i, sec in enumerate(doc["secoes"]):
        with st.expander(f"{sec['rotulo']} — {sec['titulo']}"):
            st.text_area("Texto", key=f"edit_{i}", height=300, label_visibility="collapsed")
            c1, c2 = st.columns([1, 5])
            if c1.button("Regenerar", key=f"regen_btn_{i}", help="Volta a gerar com os dados atuais do formulário"):
                st.session_state.regen = i
                st.rerun()
            if sec["fontes"]:
                c2.caption("Fontes: " + "; ".join(sec["fontes"]))

    anexo = st.checkbox("Incluir anexo de rastreabilidade (fontes consultadas, uso interno)", value=True)
    finais = [{**s, "texto": st.session_state.get(f"edit_{i}", s["texto"])} for i, s in enumerate(doc["secoes"])]
    fontes = sorted({f.split("] ", 1)[-1] for s in doc["secoes"] for f in s["fontes"]}) if anexo else None
    st.download_button(
        "Descarregar Word (.docx)",
        exportar_docx(template.nome, dados.get("objeto", ""), template.numeracao, finais, fontes),
        file_name=f"{template.id}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        type="primary",
    )


# --------------------------------------------------------------------------- consultar

def pagina_consultar() -> None:
    st.title("Consultar a base documental")
    st.caption("Perguntas sobre legislação, orientações e peças anteriores, com indicação das fontes.")
    historico = st.session_state.setdefault("chat", [])
    if historico and st.sidebar.button("Limpar conversa"):
        historico.clear()
        st.rerun()
    for m in historico:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    pergunta = st.chat_input("Ex.: Quais os prazos mínimos para apresentação de propostas num concurso público?")
    if not pergunta:
        return
    with st.chat_message("user"):
        st.markdown(pergunta)
    with st.chat_message("assistant"):
        try:
            stream, ctx = consultar(llm, store, pergunta, historico)
            resposta = escrever_stream(stream)
            with st.expander("Fontes"):
                for f in ctx.fontes():
                    st.markdown(f"- {f}")
        except Exception as e:  # noqa: BLE001
            st.error(f"Erro: {e}")
            resposta = ""
    historico += [{"role": "user", "content": pergunta}, {"role": "assistant", "content": resposta}]


# --------------------------------------------------------------------------- base documental

def pagina_base() -> None:
    st.title("Base documental")
    st.caption("Os documentos são processados e indexados no servidor onde a aplicação corre.")

    with st.form("upload", clear_on_submit=True):
        ficheiros = st.file_uploader(
            "Documentos (PDF, DOCX, TXT, MD)", type=["pdf", "docx", "txt", "md"], accept_multiple_files=True
        )
        fonte = st.selectbox("Tipo de fonte", list(FONTES), format_func=FONTES.get)
        c1, c2 = st.columns(2)
        diploma = c1.text_input(
            "Diploma (só legislação)", help="Use exatamente «CCP» para o Código dos Contratos Públicos."
        )
        tipo_peca = c2.selectbox(
            "Tipo de peça (só peças anteriores)",
            [""] + list(templates),
            format_func=lambda k: templates[k].nome if k else "—",
        )
        c3, c4, c5 = st.columns(3)
        proc = c3.selectbox("Procedimento", [""] + list(TIPOS_PROCEDIMENTO), format_func=lambda k: TIPOS_PROCEDIMENTO.get(k, "—"))
        contrato = c4.selectbox("Tipo de contrato", [""] + list(TIPOS_CONTRATO), format_func=lambda k: TIPOS_CONTRATO.get(k, "—"))
        ano = c5.text_input("Ano")
        submeter = st.form_submit_button("Indexar", type="primary")

    if submeter and ficheiros:
        if fonte == "peca" and not tipo_peca:
            st.error("Indique o tipo de peça.")
        elif fonte == "legislacao" and not diploma:
            st.error("Indique o diploma.")
        else:
            meta = {
                "fonte": fonte,
                "diploma": diploma.strip() if fonte == "legislacao" else "",
                "tipo_peca": tipo_peca if fonte == "peca" else "",
                "tipo_procedimento": proc,
                "tipo_contrato": contrato,
                "ano": ano.strip(),
            }
            meta = {k: v for k, v in meta.items() if v}
            barra = st.progress(0.0)
            for i, f in enumerate(ficheiros):
                try:
                    with st.spinner(f"A indexar {f.name}..."):
                        n = ingerir(store, f.name, f.getvalue(), meta)
                    st.success(f"{f.name}: {n} excertos indexados")
                except Exception as e:  # noqa: BLE001
                    st.error(f"{f.name}: {e}")
                barra.progress((i + 1) / len(ficheiros))

    st.subheader("Documentos indexados")
    fontes = store.listar_fontes()
    if not fontes:
        st.caption("Ainda não há documentos indexados.")
        return
    st.dataframe(fontes, hide_index=True)
    c1, c2, c3 = st.columns([3, 1, 1])
    alvo = c1.selectbox("Remover documento do índice", [f["source"] for f in fontes])
    confirmar = c2.checkbox("Confirmo a remoção")
    if c3.button("Remover", disabled=not confirmar):
        store.remover(alvo)
        st.rerun()


# --------------------------------------------------------------------------- main

if not autenticado():
    st.stop()

PAGINAS = {"Gerar peça": pagina_gerar, "Consultar": pagina_consultar, "Base documental": pagina_base}
escolha = st.sidebar.radio("Navegação", list(PAGINAS))
st.sidebar.divider()
st.sidebar.caption(f"Modelo: {settings.llm_model}\n\nExcertos indexados: {store.contar()}")
st.sidebar.caption("⚠️ O texto gerado é um rascunho e exige revisão jurídica antes de ser utilizado.")
PAGINAS[escolha]()
