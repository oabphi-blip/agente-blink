"""
Pytest — Protocolo Remarcação/Encaixe (Fábio 17/06/2026).

Unifica regra C-26 com instrução nova:
- Encaixe move pra 4.REAGENDAR (não 2.LEADS FRIO)
- Atualiza 1.PREFERÊNCIA (dia/turno/período) quando paciente menciona
- Override humano permitido
- Frase canônica de confirmação

Estes testes verificam presença textual no _MASTER_INSTRUCTION.md.
"""

from pathlib import Path

PROMPT = Path(__file__).parent.parent / "voice_agent" / "knowledge_base" / "_MASTER_INSTRUCTION.md"


def _load():
    return PROMPT.read_text(encoding="utf-8")


class TestProtocoloEncaixe:
    def test_versao_prompt_atualizada(self):
        txt = _load()
        assert "2026-06-17-protocolo-encaixe-4-reagendar" in txt, \
            "VERSAO_PROMPT não bumpada — Anthropic SDK vai servir cache antigo"

    def test_secao_e17a_resumo_protocolo_existe(self):
        txt = _load()
        assert "E1.7-A — RESUMO DO PROTOCOLO REMARCAÇÃO/ENCAIXE" in txt

    def test_3_passos_sequenciais_obrigatorios(self):
        txt = _load()
        # Passos 1, 2, 3 do bloco fornecido pelo Fábio
        assert "PREENCHER campo \"A FAZER\"" in txt
        assert "MOVER lead pra etapa \"4.REAGENDAR\"" in txt
        assert "MENSAGEM padrão de confirmação" in txt

    def test_status_id_4_reagendar_correto(self):
        txt = _load()
        assert "106184631" in txt, "status_id 4.REAGENDAR não está no prompt"

    def test_a_fazer_encaixe_referenciado(self):
        txt = _load()
        # Field A FAZER = Encaixe enum
        assert "A FAZER" in txt and "Encaixe" in txt

    def test_frase_canonica_confirmacao(self):
        txt = _load()
        # Frase do Fábio (fragmento principal)
        assert "Sua preferência foi registrada na fila de encaixe" in txt
        assert "entro em contato por aqui mesmo" in txt

    def test_atualizar_campo_preferencia(self):
        txt = _load()
        assert "1.PREFERÊNCIA" in txt
        assert "dia da semana, turno, período" in txt or \
               "dia da semana + turno + período" in txt

    def test_override_humano_permitido(self):
        txt = _load()
        assert "Override humano" in txt or "override humano" in txt.lower()
        assert "responsabilidade da equipe humana" in txt

    def test_anti_padrao_documentado(self):
        txt = _load()
        # Não deixar lead parado em 5-AGENDADO
        assert "5-AGENDADO" in txt
        # E o marcador
        assert "A FAZER = Encaixe" in txt

    def test_imprevisto_pessoal_aponta_4_reagendar(self):
        """A tabela do C-26 'imprevisto pessoal' agora aponta pra 4.REAGENDAR."""
        txt = _load()
        # Acha a linha imprevisto pessoal (COM CONVÊNIO) e confere 4.REAGENDAR
        idx = txt.find("Imprevisto pessoal**")
        assert idx > 0
        bloco = txt[idx:idx+800]
        assert "4.REAGENDAR" in bloco
        # 2.LEADS FRIO foi REMOVIDO desse bloco específico (mas continua existindo em outras seções pra cold reactivation)
        assert "2.LEADS FRIO" not in bloco, \
            "Imprevisto pessoal ainda aponta pra 2.LEADS FRIO — não atualizado"


class TestRegraOriginalC26Preservada:
    """Garantir que NÃO destruímos a árvore de investigação C-26."""

    def test_pergunta_motivo_ainda_existe(self):
        txt = _load()
        assert "posso saber o motivo da desmarcação" in txt or \
               "posso saber o motivo" in txt

    def test_4_ramos_continuam_documentados(self):
        txt = _load()
        # Imprevisto pessoal / Problema autorização / Sem interesse / Sintoma novo
        assert "Imprevisto pessoal" in txt
        assert "Problema autorização" in txt
        assert "Sem interesse" in txt
        assert "Sintoma novo" in txt

    def test_sem_interesse_continua_closed_lost(self):
        """Sem interesse NÃO deve virar encaixe — vai pra Closed-lost."""
        txt = _load()
        idx = txt.find("Sem interesse")
        assert idx > 0
        bloco = txt[idx:idx+400]
        assert "Closed-lost" in bloco

    def test_sintoma_novo_continua_atendimento_humano(self):
        txt = _load()
        idx = txt.find("Sintoma novo")
        assert idx > 0
        bloco = txt[idx:idx+400]
        assert "1-ATENDIMENTO HUMANO" in bloco
