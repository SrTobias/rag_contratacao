"""Tipologias usadas como metadados e filtros (identificador -> designação)."""

TIPOS_PROCEDIMENTO = {
    "ajuste_direto": "Ajuste direto (regime geral)",
    "ajuste_direto_simplificado": "Ajuste direto (regime simplificado)",
    "consulta_previa": "Consulta prévia",
    "concurso_publico": "Concurso público",
    "concurso_publico_urgente": "Concurso público urgente",
    "concurso_limitado": "Concurso limitado por prévia qualificação",
    "negociacao": "Procedimento de negociação",
    "dialogo_concorrencial": "Diálogo concorrencial",
    "parceria_inovacao": "Parceria para a inovação",
    "acordo_quadro": "Contrato ao abrigo de acordo-quadro",
}

TIPOS_CONTRATO = {
    "aquisicao_bens": "Aquisição de bens móveis",
    "locacao_bens": "Locação de bens móveis",
    "aquisicao_servicos": "Aquisição de serviços",
    "empreitada": "Empreitada de obras públicas",
    "concessao_obras": "Concessão de obras públicas",
    "concessao_servicos": "Concessão de serviços públicos",
    "outro": "Outro",
}

FONTES = {
    "legislacao": "Legislação",
    "orientacao": "Orientações / jurisprudência",
    "peca": "Peça de procedimento anterior",
}

# Campos comuns a todas as peças (os templates podem acrescentar campos próprios).
CAMPOS_COMUNS = [
    {"id": "entidade_adjudicante", "rotulo": "Entidade adjudicante"},
    {"id": "orgao_competente", "rotulo": "Órgão competente para a decisão de contratar"},
    {"id": "objeto", "rotulo": "Objeto do contrato", "tipo": "textarea"},
    {"id": "preco_base", "rotulo": "Preço base (€, sem IVA)"},
    {"id": "prazo_execucao", "rotulo": "Prazo de execução / vigência"},
    {"id": "cpv", "rotulo": "Código(s) CPV"},
    {"id": "lotes", "rotulo": "Lotes (se aplicável)", "tipo": "textarea"},
    {
        "id": "criterio_adjudicacao",
        "rotulo": "Critério de adjudicação (monofator preço / multifator, fatores e ponderações)",
        "tipo": "textarea",
    },
    {"id": "plataforma", "rotulo": "Plataforma eletrónica de contratação"},
    {
        "id": "informacao_adicional",
        "rotulo": "Outras informações relevantes (requisitos, caução, prazos, particularidades)",
        "tipo": "textarea",
    },
]
