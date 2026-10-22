"""Definição dos módulos da plataforma simulada (Colliers Hub).

Cada entidade descreve seus campos, e o resto do sistema (MCP, validação,
painel e auditoria) é genérico. Para criar um módulo novo, basta acrescentar
uma entrada aqui e, se quiser, dados em seed.py.

Tipos de campo: texto, texto_longo, numero, moeda, data, opcao, ref, booleano.
Marcas: obrigatorio, sistema (só a plataforma altera), sensivel (alterar pede aprovação
quando a política da entidade diz isso; editável no painel de governança).
"""

LINHAS_SERVICO = [
    "Escritórios Corporativos", "Industrial e Logística", "Mercado de Capitais",
    "Avaliações (Valuation)", "Gestão Predial", "Gestão de Projetos", "Terrenos", "Varejo",
]

ENTIDADES: dict[str, dict] = {
    # ------------------------------------------------------------ CRM
    "empresas": {
        "nome": "Empresas", "grupo": "CRM", "prefixo": "EMP", "titulo": "nome",
        "descricao": "Clientes ocupantes, proprietários, investidores, inquilinos de varejo e fornecedores.",
        "campos": {
            "nome": {"tipo": "texto", "obrigatorio": True},
            "cnpj": {"tipo": "texto"},
            "tipo": {"tipo": "opcao", "obrigatorio": True, "opcoes": ["Cliente ocupante", "Proprietário", "Investidor", "Inquilino de varejo", "Fornecedor"]},
            "setor": {"tipo": "texto"},
            "cidade": {"tipo": "texto"},
            "gerente_conta_id": {"tipo": "ref", "ref": "colaboradores", "rotulo": "Gerente da conta"},
            "observacoes": {"tipo": "texto_longo"},
        },
        "colunas": ["nome", "tipo", "setor", "cidade", "gerente_conta_id"],
    },
    "contatos": {
        "nome": "Contatos", "grupo": "CRM", "prefixo": "CON", "titulo": "nome",
        "descricao": "Pessoas das empresas: decisores, financeiro, facilities.",
        "campos": {
            "empresa_id": {"tipo": "ref", "ref": "empresas", "obrigatorio": True},
            "nome": {"tipo": "texto", "obrigatorio": True},
            "cargo": {"tipo": "texto"},
            "email": {"tipo": "texto"},
            "telefone": {"tipo": "texto"},
            "principal": {"tipo": "booleano"},
        },
        "colunas": ["nome", "empresa_id", "cargo", "email"],
    },
    "oportunidades": {
        "nome": "Oportunidades", "grupo": "CRM", "prefixo": "OPP", "titulo": "titulo",
        "descricao": "Funil comercial. responsavel_id é o colaborador ou time que conduz o negócio; trocar o responsável é um encaminhamento.",
        "campos": {
            "titulo": {"tipo": "texto", "obrigatorio": True},
            "empresa_id": {"tipo": "ref", "ref": "empresas", "obrigatorio": True},
            "linha_servico": {"tipo": "opcao", "opcoes": LINHAS_SERVICO, "rotulo": "Linha de serviço"},
            "estagio": {"tipo": "opcao", "obrigatorio": True, "opcoes": ["Prospecção", "Qualificação", "Proposta", "Negociação", "Ganha", "Perdida"]},
            "valor_estimado": {"tipo": "moeda", "rotulo": "Valor estimado (honorários)"},
            "responsavel_id": {"tipo": "ref", "ref": "colaboradores", "rotulo": "Responsável", "sensivel": True},
            "origem": {"tipo": "opcao", "opcoes": ["Indicação", "Base de clientes", "Vencimento de contrato", "Site", "Evento", "Venda cruzada", "Prospecção ativa"]},
            "descricao": {"tipo": "texto_longo"},
            "proximo_passo": {"tipo": "texto"},
            "data_proximo_passo": {"tipo": "data"},
        },
        "colunas": ["titulo", "empresa_id", "linha_servico", "estagio", "valor_estimado", "responsavel_id"],
    },
    "interacoes": {
        "nome": "Interações", "grupo": "CRM", "prefixo": "INT", "titulo": "resumo",
        "descricao": "Reuniões, ligações, visitas e e-mails registrados no CRM.",
        "campos": {
            "empresa_id": {"tipo": "ref", "ref": "empresas", "obrigatorio": True},
            "oportunidade_id": {"tipo": "ref", "ref": "oportunidades"},
            "tipo": {"tipo": "opcao", "obrigatorio": True, "opcoes": ["Reunião", "Ligação", "Visita", "E-mail", "Mensagem"]},
            "data": {"tipo": "data", "obrigatorio": True},
            "colaborador_id": {"tipo": "ref", "ref": "colaboradores"},
            "resumo": {"tipo": "texto_longo", "obrigatorio": True},
            "proximos_passos": {"tipo": "texto"},
        },
        "colunas": ["data", "tipo", "empresa_id", "oportunidade_id", "resumo"],
    },
    # ------------------------------------------------------------ Carteira
    "imoveis": {
        "nome": "Imóveis", "grupo": "Carteira", "prefixo": "IMV", "titulo": "nome",
        "descricao": "Ativos: escritórios, galpões, shoppings e terrenos, administrados ou comercializados pela Colliers.",
        "campos": {
            "nome": {"tipo": "texto", "obrigatorio": True},
            "tipo": {"tipo": "opcao", "obrigatorio": True, "opcoes": ["Escritório", "Galpão logístico", "Shopping / varejo", "Terreno", "Uso misto"]},
            "classe": {"tipo": "opcao", "opcoes": ["AAA", "AA", "A", "B", "C", "Não se aplica"]},
            "endereco": {"tipo": "texto"},
            "cidade": {"tipo": "texto", "obrigatorio": True},
            "area_total_m2": {"tipo": "numero", "rotulo": "Área total (m²)"},
            "vago_m2": {"tipo": "numero", "rotulo": "Área vaga (m²)"},
            "proprietario_id": {"tipo": "ref", "ref": "empresas", "rotulo": "Proprietário"},
            "administrado_pela_colliers": {"tipo": "booleano", "rotulo": "Administrado pela Colliers"},
            "preco_pedido_m2": {"tipo": "moeda", "rotulo": "Aluguel pedido (R$/m²)"},
        },
        "colunas": ["nome", "tipo", "classe", "cidade", "area_total_m2", "vago_m2"],
    },
    "contratos": {
        "nome": "Contratos", "grupo": "Carteira", "prefixo": "CTR", "titulo": "unidade",
        "descricao": "Contratos de locação. Os campos são o cadastro; o campo texto e os aditivos são o documento. Aditivos prevalecem sobre o cadastro.",
        "campos": {
            "imovel_id": {"tipo": "ref", "ref": "imoveis", "obrigatorio": True},
            "unidade": {"tipo": "texto", "obrigatorio": True},
            "locatario_id": {"tipo": "ref", "ref": "empresas", "obrigatorio": True, "rotulo": "Locatário"},
            "locador_id": {"tipo": "ref", "ref": "empresas", "rotulo": "Locador"},
            "area_m2": {"tipo": "numero", "rotulo": "Área (m²)"},
            "inicio": {"tipo": "data", "obrigatorio": True},
            "vencimento": {"tipo": "data", "obrigatorio": True},
            "aluguel_mensal": {"tipo": "moeda"},
            "indice_reajuste": {"tipo": "opcao", "opcoes": ["IPCA", "IGP-M", "IVAR"]},
            "aviso_previo": {"tipo": "texto", "rotulo": "Aviso prévio de renovação"},
            "renovacao_automatica": {"tipo": "booleano"},
            "status": {"tipo": "opcao", "opcoes": ["Vigente", "Em renovação", "Encerrado"]},
            "texto": {"tipo": "texto_longo", "rotulo": "Texto do contrato"},
        },
        "colunas": ["unidade", "imovel_id", "locatario_id", "vencimento", "aluguel_mensal", "status"],
        "virtuais": ["dias_para_vencimento"],
    },
    "aditivos": {
        "nome": "Aditivos", "grupo": "Carteira", "prefixo": "ADT", "titulo": "resumo",
        "descricao": "Termos aditivos e distratos. Alteram o contrato original.",
        "campos": {
            "contrato_id": {"tipo": "ref", "ref": "contratos", "obrigatorio": True},
            "numero": {"tipo": "numero"},
            "assinado_em": {"tipo": "data"},
            "resumo": {"tipo": "texto", "obrigatorio": True},
            "texto": {"tipo": "texto_longo"},
        },
        "colunas": ["contrato_id", "numero", "assinado_em", "resumo"],
    },
    "alertas": {
        "nome": "Datas críticas", "grupo": "Carteira", "prefixo": "ALR", "titulo": "descricao",
        "descricao": "Alertas de datas críticas de contratos: renovação, reajuste, vencimento, saída antecipada.",
        "campos": {
            "contrato_id": {"tipo": "ref", "ref": "contratos", "obrigatorio": True},
            "data": {"tipo": "data", "obrigatorio": True},
            "tipo": {"tipo": "opcao", "obrigatorio": True, "opcoes": ["Renovação", "Reajuste", "Vencimento", "Saída antecipada", "Outro"]},
            "descricao": {"tipo": "texto", "obrigatorio": True},
            "responsavel_id": {"tipo": "ref", "ref": "colaboradores"},
            "status": {"tipo": "opcao", "opcoes": ["Aberto", "Concluído"]},
        },
        "colunas": ["data", "tipo", "contrato_id", "descricao", "status"],
        "virtuais": ["dias_ate"],
    },
    # ------------------------------------------------------------ Operação
    "cobrancas": {
        "nome": "Cobranças", "grupo": "Operação", "prefixo": "COB", "titulo": "competencia",
        "descricao": "Aluguéis e encargos dos imóveis administrados. dias_atraso é calculado pela plataforma.",
        "campos": {
            "contrato_id": {"tipo": "ref", "ref": "contratos", "obrigatorio": True},
            "locatario_id": {"tipo": "ref", "ref": "empresas", "rotulo": "Locatário"},
            "competencia": {"tipo": "texto", "obrigatorio": True, "rotulo": "Competência (AAAA-MM)"},
            "vencimento": {"tipo": "data", "obrigatorio": True},
            "valor": {"tipo": "moeda", "obrigatorio": True, "sensivel": True},
            "status": {"tipo": "opcao", "obrigatorio": True, "opcoes": ["Em aberto", "Paga", "Em negociação", "Acordo fechado", "Enviada ao jurídico"], "sensivel": True},
            "ultimo_contato": {"tipo": "data"},
            "observacoes": {"tipo": "texto_longo"},
        },
        "colunas": ["locatario_id", "competencia", "vencimento", "valor", "status"],
        "virtuais": ["dias_atraso"],
    },
    "chamados": {
        "nome": "Chamados", "grupo": "Operação", "prefixo": "CHM", "titulo": "descricao",
        "descricao": "Chamados de manutenção dos imóveis administrados (Gestão Predial).",
        "campos": {
            "imovel_id": {"tipo": "ref", "ref": "imoveis", "obrigatorio": True},
            "empresa_id": {"tipo": "ref", "ref": "empresas", "rotulo": "Solicitante (empresa)"},
            "solicitante": {"tipo": "texto"},
            "categoria": {"tipo": "opcao", "opcoes": ["Ar-condicionado", "Elétrica", "Hidráulica", "Elevadores", "Segurança", "Limpeza", "Civil", "Outros"]},
            "descricao": {"tipo": "texto_longo", "obrigatorio": True},
            "prioridade": {"tipo": "opcao", "opcoes": ["Baixa", "Média", "Alta", "Urgente"]},
            "status": {"tipo": "opcao", "opcoes": ["Aberto", "Em atendimento", "Aguardando fornecedor", "Concluído"]},
            "fornecedor_id": {"tipo": "ref", "ref": "empresas", "rotulo": "Fornecedor"},
            "custo_estimado": {"tipo": "moeda", "sensivel": True},
            "aberto_em": {"tipo": "data"},
        },
        "colunas": ["aberto_em", "imovel_id", "categoria", "prioridade", "status", "descricao"],
    },
    "demandas": {
        "nome": "Caixa de entrada", "grupo": "Operação", "prefixo": "DEM", "titulo": "assunto",
        "descricao": "Pedidos que chegam por e-mail, Teams, telefone ou site e ainda precisam de triagem.",
        "campos": {
            "canal": {"tipo": "opcao", "opcoes": ["E-mail", "Teams", "Telefone", "Site", "WhatsApp"]},
            "recebida_em": {"tipo": "data"},
            "remetente": {"tipo": "texto"},
            "empresa_id": {"tipo": "ref", "ref": "empresas"},
            "assunto": {"tipo": "texto", "obrigatorio": True},
            "mensagem": {"tipo": "texto_longo", "obrigatorio": True},
            "categoria": {"tipo": "opcao", "opcoes": ["Não classificada", "Locação de escritório", "Industrial e logística", "Manutenção predial", "Avaliação de imóvel", "Investimento / venda de ativo", "Jurídico / contratual", "Financeiro / cobrança", "Fora do escopo"]},
            "prioridade": {"tipo": "opcao", "opcoes": ["Não definida", "Baixa", "Média", "Alta", "Urgente"]},
            "encaminhada_para_id": {"tipo": "ref", "ref": "colaboradores", "rotulo": "Encaminhada para"},
            "status": {"tipo": "opcao", "opcoes": ["Nova", "Em triagem", "Encaminhada", "Respondida", "Arquivada"]},
            "nota_triagem": {"tipo": "texto_longo", "rotulo": "Nota de triagem"},
        },
        "colunas": ["recebida_em", "canal", "remetente", "assunto", "categoria", "status"],
    },
    "tarefas": {
        "nome": "Agenda e tarefas", "grupo": "Operação", "prefixo": "TAR", "titulo": "titulo",
        "descricao": "Vistorias, reuniões, follow-ups e prazos da equipe.",
        "campos": {
            "titulo": {"tipo": "texto", "obrigatorio": True},
            "tipo": {"tipo": "opcao", "opcoes": ["Vistoria", "Reunião", "Ligação", "Follow-up", "Prazo", "Outro"]},
            "data": {"tipo": "data", "obrigatorio": True},
            "hora": {"tipo": "texto", "rotulo": "Hora (HH:MM)"},
            "responsavel_id": {"tipo": "ref", "ref": "colaboradores"},
            "relacionado_a": {"tipo": "texto", "rotulo": "Relacionado a (id)"},
            "status": {"tipo": "opcao", "opcoes": ["Pendente", "Concluída", "Cancelada"]},
            "descricao": {"tipo": "texto_longo"},
        },
        "colunas": ["data", "hora", "tipo", "titulo", "responsavel_id", "status"],
        "virtuais": ["dias_ate"],
    },
    "comunicacoes": {
        "nome": "Comunicações", "grupo": "Operação", "prefixo": "COM", "titulo": "assunto",
        "descricao": "E-mails e cartas para clientes, locatários e locadores. Criar só gera rascunho; quem envia é a ferramenta enviar_comunicacao.",
        "campos": {
            "tipo": {"tipo": "opcao", "obrigatorio": True, "opcoes": ["E-mail", "Carta", "Notificação formal"]},
            "empresa_id": {"tipo": "ref", "ref": "empresas", "rotulo": "Destinatário (empresa)"},
            "para": {"tipo": "texto", "obrigatorio": True, "rotulo": "Para (nome e e-mail)"},
            "assunto": {"tipo": "texto", "obrigatorio": True},
            "corpo": {"tipo": "texto_longo", "obrigatorio": True},
            "relacionado_a": {"tipo": "texto", "rotulo": "Relacionado a (id)"},
            "status": {"tipo": "opcao", "opcoes": ["Rascunho", "Aguardando aprovação", "Enviada", "Cancelada"], "sistema": True},
            "enviada_em": {"tipo": "data", "sistema": True},
        },
        "colunas": ["tipo", "para", "assunto", "relacionado_a", "status"],
    },
    # ------------------------------------------------------------ Referência
    "conhecimento": {
        "nome": "Base de conhecimento", "grupo": "Referência", "prefixo": "KB", "titulo": "titulo",
        "descricao": "Políticas, procedimentos, tabelas de decisão e modelos internos da Colliers. Fonte para os agentes seguirem as regras da área.",
        "campos": {
            "titulo": {"tipo": "texto", "obrigatorio": True},
            "categoria": {"tipo": "opcao", "opcoes": ["Política", "Procedimento", "Tabela de decisão", "Modelo de documento", "Perguntas frequentes"]},
            "area": {"tipo": "texto"},
            "conteudo": {"tipo": "texto_longo", "obrigatorio": True},
        },
        "colunas": ["titulo", "categoria", "area"],
    },
    "colaboradores": {
        "nome": "Colaboradores", "grupo": "Referência", "prefixo": "COL", "titulo": "nome",
        "descricao": "Pessoas e times da Colliers, com linha de serviço. Use os ids como responsáveis.",
        "campos": {
            "nome": {"tipo": "texto", "obrigatorio": True},
            "cargo": {"tipo": "texto"},
            "linha_servico": {"tipo": "opcao", "opcoes": LINHAS_SERVICO + ["Diretoria", "Jurídico", "Financeiro"]},
            "email": {"tipo": "texto"},
            "cidade": {"tipo": "texto"},
        },
        "colunas": ["nome", "cargo", "linha_servico", "cidade"],
    },
}

# Política padrão por entidade e operação: livre, aprovacao ou bloqueado.
# "sensiveis_pedem_aprovacao": alterar um campo marcado como sensível vai para aprovação
# mesmo quando atualizar é livre.
POLITICAS_PADRAO: dict[str, dict] = {
    "empresas":      {"criar": "livre", "atualizar": "livre", "excluir": "aprovacao"},
    "contatos":      {"criar": "livre", "atualizar": "livre", "excluir": "aprovacao"},
    "oportunidades": {"criar": "livre", "atualizar": "livre", "excluir": "aprovacao"},
    "interacoes":    {"criar": "livre", "atualizar": "livre", "excluir": "aprovacao"},
    "imoveis":       {"criar": "aprovacao", "atualizar": "livre", "excluir": "bloqueado"},
    "contratos":     {"criar": "aprovacao", "atualizar": "aprovacao", "excluir": "bloqueado"},
    "aditivos":      {"criar": "aprovacao", "atualizar": "aprovacao", "excluir": "bloqueado"},
    "alertas":       {"criar": "livre", "atualizar": "livre", "excluir": "livre"},
    "cobrancas":     {"criar": "aprovacao", "atualizar": "livre", "excluir": "bloqueado"},
    "chamados":      {"criar": "livre", "atualizar": "livre", "excluir": "aprovacao"},
    "demandas":      {"criar": "livre", "atualizar": "livre", "excluir": "aprovacao"},
    "tarefas":       {"criar": "livre", "atualizar": "livre", "excluir": "livre"},
    "comunicacoes":  {"criar": "livre", "atualizar": "livre", "excluir": "livre"},
    "conhecimento":  {"criar": "aprovacao", "atualizar": "aprovacao", "excluir": "bloqueado"},
    "colaboradores": {"criar": "bloqueado", "atualizar": "bloqueado", "excluir": "bloqueado"},
}
ACOES_PADRAO = {"enviar_comunicacao": "aprovacao"}

MODOS = ["livre", "aprovacao", "bloqueado"]
