"""Knowledge base local com retrieval por palavras-chave.

Carrega os artigos .md da pasta knowledge_base e seleciona os mais relevantes
para cada mensagem do paciente. O artigo selecionado é injetado no prompt do
GPT, fazendo papel de RAG simples (sem embeddings/vetores — keyword matching
pesado de termos da própria clínica).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

KB_DIR = Path(__file__).resolve().parent / "knowledge_base"


# Termos-chave por artigo. Cada hit conta como 1 ponto de relevância.
ARTICLE_KEYWORDS: dict[str, list[str]] = {
    "00_identidade_e_unidades.md": [
        "endereço", "endereco", "unidade", "asa norte", "aguas claras",
        "agua claras", "felicittá", "felicitta", "medical center", "onde fica",
        "como chegar", "estacionamento", "mapa", "localização", "localizacao",
        "horario funcionamento", "horários", "segunda", "terça", "quarta",
        "quinta", "sexta",
    ],
    "01_medicos_e_especialidades.md": [
        "médico", "medico", "doutora", "doutor", "dra karla", "dra. karla",
        "karla", "delalibera", "kátia", "katia", "fabricio", "fabrício",
        "freitas", "especialidade", "especialista", "oftalmologista",
        "oftalmopediatra", "qual médico",
    ],
    "02_convenios_e_valores.md": [
        "convênio", "convenio", "plano", "plano de saúde", "plano saude",
        "particular", "valor", "preço", "preco", "quanto custa", "tabela",
        "pagamento", "pix", "cartão", "cartao", "parcelar", "parcelamento",
        "incentivo", "bradesco", "amil", "unimed", "saúde caixa", "saude caixa",
        "geap", "fusex", "pró-saúde", "pro-saude", "cassi",
    ],
    "03_lentes_de_contato.md": [
        "lente", "lentes", "lente de contato", "lentes de contato",
        "adaptação", "adaptacao", "lente teste", "gelatinosa", "tórica",
        "torica", "rígida", "rigida", "gás-permeável", "minhas lentes",
        "encomenda", "ceratocone",
    ],
    "04_oftalmopediatria.md": [
        "filho", "filha", "criança", "crianca", "bebê", "bebe", "escola",
        "escolar", "professora", "infantil", "pediatra", "oftalmopediatria",
        "oftalmopediatra", "menino", "menina", "anos de idade", "anos",
    ],
    "05_catarata_e_cirurgias.md": [
        "catarata", "cirurgia", "operação", "operacao", "lente intraocular",
        "lio", "monofocal", "multifocal", "estrabismo", "olho desviado",
        "vesgo", "olho preguiçoso", "preguicoso", "sdp", "deficiência postural",
        "deficiencia postural", "pós-operatório", "pos-operatorio",
    ],
    "06_exames_complementares.md": [
        "exame", "mapeamento", "retina", "fundo de olho", "topografia",
        "oct", "campo visual", "paquimetria", "biometria", "retinografia",
        "dilatação", "dilatacao", "dilatar", "pedido médico", "pedido medico",
    ],
    "07_urgencia.md": [
        "urgência", "urgencia", "emergência", "emergencia", "socorro",
        "agora", "imediato", "dor forte", "dor intensa", "perdi a visão",
        "perdi visão", "perdi visao", "trauma", "batida no olho",
        "respingo", "químico", "quimico", "queimadura", "flashes",
        "moscas volantes", "sangrando", "secreção", "secrecao",
        "muito vermelho", "não consigo abrir", "nao consigo abrir",
    ],
    "08_audio_e_escalonamento.md": [
        "humano", "atendente", "pessoa", "pessoa de verdade", "falar com alguém",
        "falar com alguem", "reclamar", "reclamação", "reclamacao", "reembolso",
        "laudo", "atestado", "recibo",
    ],
    "09_remarcacao_e_lembretes.md": [
        "remarcar", "remarcacao", "remarcação", "cancelar", "cancelamento",
        "desmarcar", "trocar dia", "trocar horário", "trocar horario",
        "não vou poder ir", "nao vou poder ir", "imprevisto", "viagem",
        "doente", "esqueci", "lembrete", "confirmar consulta",
        "amanhã", "amanha",
    ],
    "10_reativacao_leads.md": [
        "voltei", "retornei", "ainda dá", "ainda da", "sumido", "muito tempo",
        "ano novo", "aniversário", "aniversario",
    ],
    "11_tom_e_conversao.md": [
        # Transversal — incluído sempre. Sem keywords.
    ],
    "12_funil_vendas_catarata.md": [
        "catarata", "cirurgia de catarata", "cirurgia catarata",
        "lente intraocular", "lio", "monofocal", "multifocal", "edof",
        "dr fabrício", "dr fabricio", "fabricio freitas", "fabrício freitas",
        "preciso operar", "tenho indicação", "tenho indicacao",
        "visão embaçada", "visao embacada", "halo", "vista embaçada",
        "dificuldade dirigir noite",
    ],
    "13_funil_com_convenio.md": [
        "tenho convênio", "tenho convenio", "meu convênio", "meu convenio",
        "uso plano", "plano de saúde", "plano saude",
        "amil", "bradesco", "unimed", "saude caixa", "saúde caixa",
        "geap", "fusex", "cassi", "pró-saúde", "pro-saude",
        "carteirinha", "autorização", "autorizacao", "guia",
        "definir unidade",
    ],
    "14_funil_sem_convenio.md": [
        "particular", "sem convênio", "sem convenio", "não tenho plano",
        "nao tenho plano", "vou pagar particular",
        "valor consulta", "qual o valor", "quanto custa consulta",
        "611", "670", "está caro", "esta caro", "muito caro",
        "falta de tempo", "não tenho tempo", "nao tenho tempo",
        "rotina apertada",
    ],
    "15_pagamento_pos_consulta.md": [
        "pix", "boleto", "parcela antecipada", "reserva 50", "50%",
        "comprovante", "estorno", "nota fiscal", "nf", "recibo",
        "google avaliação", "google avaliacao", "avaliação google",
        "pagamento total", "quitação", "quitacao",
    ],
    "16_ativacao_e_reativacao.md": [
        "voltei", "ainda dá", "ainda da", "esqueci", "sumi",
        "aniversário", "aniversario", "feliz aniversário",
        "sábado", "sabado", "fim de semana",
        "final do ano", "dezembro", "ano novo",
        "novo horário", "novo horario", "abriu vaga",
        "veja de novo", "antecipe", "voltando por aqui",
    ],
    "17_convenios_aceitos_lista_oficial.md": [
        # CONVÊNIOS ACEITOS — keywords para cada um
        "anafe", "bacen", "banco central",
        "care plus", "careplus",
        "casec", "codevasf",
        "casembrapa", "embrapa",
        "conab",
        "e-vida", "e vida", "luminar",
        "fascal",
        "gravia",
        "omint",
        "pf saude", "pf saúde", "polícia federal", "policia federal",
        "plan assiste", "mpf", "mpu", "mpt", "mpdft",
        "petrobras", "petrobrás",
        "plas jmu", "plas/jmu",
        "prosaude", "pro-saude", "pró-saúde", "camara dos deputados", "câmara dos deputados",
        "proasa",
        "pro ser", "proser", "stj pro ser", "stj proser",
        "pro-social trf", "trf",
        "saude caixa", "saúde caixa", "caixa",
        "serpro",
        "sis senado", "senado",
        "stf-med", "stf med", "stfmed", "stf",
        "stm plas", "stm",
        "tj dft", "tjdft", "tj-dft",
        "tre saúde", "tre saude",
        "trt saúde", "trt saude",
        "tst",
        # Termos genéricos que devem disparar a lista p/ desambiguação
        "tribunal", "tribunais", "justiça", "justica", "judiciário", "judiciario",
        "convênio", "convenio", "plano", "credenciado", "credenciamento",
        "aceita", "aceitam", "atende plano", "atendem plano",
    ],
    "22_agenda_dra_karla.md": [
        "agenda karla", "agendar karla", "dia karla", "horário karla",
        "horario karla", "encaixe karla", "janela karla",
    ],
    "23_exames_catarata_3_baloes.md": [
        "exames catarata", "incluso catarata", "o que está incluso catarata",
        "tonometria catarata", "biomicroscopia", "mapeamento dr fabricio",
    ],
    "24_faixa_investimento_cirurgia.md": [
        "valor cirurgia", "preço cirurgia", "faixa investimento",
        "faixa de investimento", "perfil 1", "perfil 2", "perfil 3",
        "lente premium", "lente multifocal", "independência óculos",
        "independencia oculos", "5.800", "7.500", "13.000", "15.000",
    ],
    "25_data_aniversario_recomendacao.md": [
        "data de nascimento", "nascimento", "idade", "anos",
        "aniversário", "aniversario", "quantos anos",
        "bebê", "bebe", "criança pequena", "crianca pequena",
        "semestral", "anual", "check-up", "checkup",
    ],
    "26_triagem_incentivos_karla.md": [
        "triagem karla", "incentivo karla", "pediatria karla",
        "estrabismo karla", "sdp karla",
        "minha filha", "meu filho", "filha está reclamando", "filho está reclamando",
    ],
    "27_encerramento_passivo.md": [
        "pode encaminhar", "ok pode", "confirmo", "tudo certo",
        "pode finalizar", "obrigado pelo atendimento", "obrigada pelo atendimento",
        "agradeço", "agradeco", "fechado",
    ],
    "28_curriculo_dra_katia.md": [
        "currículo katia", "curriculo katia", "formação katia",
        "quem é dra kátia", "quem e dra katia",
        "credenciais katia", "experiência katia",
    ],
    "29_atividades_cientificas_katia.md": [
        "atividades científicas", "atividades cientificas",
        "congressos katia", "palestras katia",
    ],
    "30_trabalhos_publicados_katia.md": [
        "publicações katia", "publicacoes katia", "jama", "revistas",
        "trabalhos publicados", "produção científica", "producao cientifica",
        "johns hopkins",
    ],
    "31_sdp_fluxo_excecao.md": [
        "sdp", "síndrome deficiência postural", "sindrome deficiencia postural",
        "deficiência postural", "deficiencia postural",
        "prisma", "lente prisma", "óculos prisma",
        "tontura", "instabilidade", "equilíbrio", "equilibrio",
        "postura", "dor postural", "dores posturais",
        "tensão pescoço", "tensao pescoco",
    ],
    "32_atendimento_catarata_completo.md": [
        "tenho catarata", "diagnosticaram catarata", "quero operar catarata",
        "fabricio freitas", "fabrício freitas", "dr fabrício", "dr fabricio",
        "agenda inteligente",
    ],
    "33_bloqueio_preco_cirurgia_catarata.md": [
        "valor da cirurgia", "preço da cirurgia", "preco da cirurgia",
        "quanto custa cirurgia", "valor lente intraocular",
        "valor lentes catarata", "preço lentes catarata",
    ],
    "34_agenda_dr_fabricio.md": [
        "agenda fabricio", "agenda fabrício", "horário fabricio",
        "horario fabricio", "encaixe fabricio", "vaga fabricio",
        "quando atende fabricio",
    ],
    "35_duvida_antecipada_convenio_pivo.md": [
        "vocês aceitam o plano", "voces aceitam o plano",
        "vocês aceitam convênio", "voces aceitam convenio",
        "atendem por convênio", "atendem por convenio",
        "funciona com a", "aceita meu plano",
    ],
    "36_pagamento_exclusivo_encaixe_karla.md": [
        "reserva exclusiva", "fila de encaixe", "encaixe perfeito",
        "adiantamento", "50% reserva", "agendamento exclusivo karla",
        "como funciona o agendamento",
    ],
    "37_escalonamento_humano.md": [
        "falar com humano", "atendente humano", "pessoa de verdade",
        "atendimento humano", "humano por favor",
        "reclamar", "reclamação", "reclamacao",
        "laudo", "atestado", "segunda via",
    ],
    "20_cirurgia_estrabismo.md": [
        "estrabismo", "olho desviado", "olho torto", "vesgo", "vesga",
        "olho preguiçoso", "olho preguicoso", "ambliopia",
        "cirurgia de estrabismo", "rafaela ortiga", "concierge estrabismo",
        "desvio ocular", "desvio do olho",
    ],
    "21_avaliacao_cirurgia_catarata_script.md": [
        "avaliação catarata", "avaliacao catarata", "consulta catarata",
        "quero operar catarata", "quero saber sobre catarata",
        "consulta dr fabricio", "consulta dr fabrício",
        "tenho catarata", "diagnóstico catarata",
    ],
    "19_tabela_valores_travas_por_medico.md": [
        "valor consulta", "qual o valor", "quanto custa", "preço consulta",
        "preco consulta", "tabela", "honorário", "honorario",
        "r$ 297", "r$ 611", "r$ 670", "r$ 800",
        "fabricio", "fabrício", "karla", "katia", "kátia",
        "sdp", "síndrome postural", "sindrome postural",
        "cirurgia estrabismo", "valor cirurgia",
        "mapeamento retina", "mapeamento de retina",
        "isenção", "isencao", "reembolso",
    ],
    "18_convenios_NAO_aceitos_lista_oficial.md": [
        # CONVÊNIOS NÃO ACEITOS — keywords (prioridade ALTA)
        "amil",
        "afeb", "afego",
        "assefaz",
        "asete", "aste",
        "bradesco", "bradesco saúde", "bradesco saude",
        "brb",
        "cassi",
        "caeme",
        "caesan",
        "camed",
        "cnti",
        "eletronorte",
        "embratel",
        "fusex",
        "fapes bnds", "fapes", "bndes", "bnds",
        "geap",
        "golden", "golden cross",
        "hapvida", "hap vida", "hap-vida",
        "inas gdf", "gdf inas", "inas-gdf", "inas",
        "notre dame", "notredame", "notre dame intermédica",
        "porto seguro",
        "quality",
        "sul américa", "sul america", "sulamérica", "sulamerica",
        "sus",
        "unimed",
        "unafisco", "sindifisco",
    ],
}

# Artigo sempre incluído (tom/identidade/conversão) como guia transversal
ALWAYS_INCLUDE = "11_tom_e_conversao.md"


def _normalize(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    # Remove acentos pra match permissivo
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return text


@dataclass
class Article:
    filename: str
    title: str
    content: str

    def __str__(self) -> str:
        return f"# {self.title}\n\n{self.content}"


class KnowledgeBase:
    def __init__(self, kb_dir: Path = KB_DIR):
        self.kb_dir = kb_dir
        self._articles: dict[str, Article] = {}
        self._normalized_keywords: dict[str, list[str]] = {
            name: [_normalize(k) for k in kws]
            for name, kws in ARTICLE_KEYWORDS.items()
        }
        self._load()

    def _load(self) -> None:
        if not self.kb_dir.is_dir():
            return
        for path in sorted(self.kb_dir.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            # Título = primeira linha que começa com #
            title_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
            title = title_match.group(1).strip() if title_match else path.stem
            self._articles[path.name] = Article(
                filename=path.name, title=title, content=text
            )

    @property
    def articles(self) -> list[Article]:
        return list(self._articles.values())

    def select_relevant(
        self, text: str, max_articles: int = 3, max_chars: int = 12000
    ) -> list[Article]:
        """Retorna os artigos mais relevantes para a mensagem do paciente.

        - Sempre inclui o artigo de TOM E CONVERSÃO como guia transversal.
        - Inclui o artigo de URGÊNCIA se a mensagem tem qualquer keyword
          de urgência (regra de segurança).
        - Pontua os demais por número de keywords matched.
        """
        normalized = _normalize(text or "")
        scores: dict[str, int] = {}

        urgency_file = "07_urgencia.md"
        urgency_keywords = self._normalized_keywords.get(urgency_file, [])
        has_urgency = any(k in normalized for k in urgency_keywords)

        for filename, kws in self._normalized_keywords.items():
            if filename == ALWAYS_INCLUDE:
                continue
            if not kws:
                continue
            score = sum(1 for k in kws if k in normalized)
            if score > 0:
                scores[filename] = score

        # Seleção final
        selected: list[str] = []
        if has_urgency and urgency_file in self._articles:
            selected.append(urgency_file)

        for filename, _score in sorted(
            scores.items(), key=lambda kv: kv[1], reverse=True
        ):
            if filename not in selected:
                selected.append(filename)
            if len(selected) >= max_articles:
                break

        # Sempre o guia de tom como fechamento
        if ALWAYS_INCLUDE in self._articles and ALWAYS_INCLUDE not in selected:
            selected.append(ALWAYS_INCLUDE)

        # Corta por tamanho (proteção)
        out: list[Article] = []
        total = 0
        for fn in selected:
            art = self._articles[fn]
            if total + len(art.content) > max_chars and out:
                break
            out.append(art)
            total += len(art.content)
        return out

    def format_for_prompt(self, articles: Iterable[Article]) -> str:
        parts = []
        for a in articles:
            parts.append(f"\n=== {a.title} ===\n{a.content}\n")
        return "\n".join(parts)
