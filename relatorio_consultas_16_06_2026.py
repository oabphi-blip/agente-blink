"""Gera PDF — Relação Completa Consultas 16/06/2026 · Dra. Karla Delalíbera · Águas Claras."""
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
)

OUTPUT = "relatorio_consultas_16_06_2026.pdf"

# ============================================================
# Dados
# ============================================================

CABECALHO_TITULO = "Relação Completa — Consultas 16/06/2026"
CABECALHO_SUBTITULO = "Dra. Karla Delalíbera Pacheco · Águas Claras"
GERADO_EM = "Gerado em 16/06/2026 às 16:35 BRT · Fonte: Medware + Kommo"

RESUMO = [
    ("Total agendamentos", "14"),
    ("Realizados ✓", "10 (71%)"),
    ("Em atendimento", "1"),
    ("Confirmados aguardando", "2"),
    ("Agendados sem confirmação", "1"),
    ("Cancelamentos", "0"),
]

# (Hora, Paciente, Idade, Plano, Status Medware, Etapa Kommo, Lead Kommo ID)
LINHAS = [
    ("08:30", "Nicolas Morales Monteiro", "2a", "Saúde Caixa", "✓ Realizado", "8-Realizado", "24017039"),
    ("09:00", "Namera Roberta Souto Ribeiro", "37a", "TJDFT", "✓ Realizado", "8-Realizado", "22604918"),
    ("09:30", "Giulliana Santos da Silva", "23a", "TRF", "✓ Realizado", "8-Realizado", "22692648"),
    ("10:00", "Summaia Garzedin Santos de Abreu", "66a", "Serpro", "✓ Realizado", "8-Realizado", "23863262"),
    ("14:00", "Thiago Andre Pierobom de Avila", "49a", "Plan Assiste", "✓ Realizado", "8-Realizado", "22968530"),
    ("14:30", "Melissa Quintino Miranda ⚭", "7a", "Care Plus", "✓ Realizado", "8-Realizado", "24141776"),
    ("15:00", "Maria Flor Quintino Miranda ⚭", "9a", "Care Plus", "✓ Realizado", "8-Realizado", "24141776"),
    ("15:30", "Ryan Lucas Assunção Alves ⚭", "8a", "Saúde Caixa", "✓ Realizado", "5-Agendado ⚠", "24153298"),
    ("16:00", "Iara Keile Assunção Silva Alves ⚭", "38a", "Saúde Caixa", "✓ Realizado", "5-Agendado ⚠", "24153298"),
    ("16:00", "Mariana de Andrade Lima", "40a", "TJDFT", "✓ Realizado", "Status 106157327", "23943914"),
    ("16:30", "Gabriela Castro Silva", "18a", "Saúde Caixa", "● Em atendimento", "Closed-won (3 dup)", "21768459"),
    ("17:00", "Bento Caetano dos Reis ⚠", "5 meses", "CORTESIA Part.", "○ Agendado", "5-Agendado", "24118612"),
    ("17:00", "Milza de Castro Santana", "—", "Saúde Caixa", "◐ Confirmado", "❌ Sem Kommo", "—"),
    ("17:30", "Dominicky Ferreira Lemos", "9a", "Particular R$ 670", "◐ Confirmado", "5-Agendado", "22345722"),
]

ALERTAS = [
    ("1. Ryan + Iara (família) — etapa errada no Kommo",
     "Consultas realizadas no Medware (status 5), mas Kommo ainda em <b>5-Agendado</b>. Mover pra 8-Realizado."),
    ("2. Milza de Castro Santana — sem lead Kommo",
     "Cadastrada direto no Medware, sem passagem pelo funil Kommo. Sem rastreabilidade."),
    ("3. Bento Caetano (5 meses) — anomalia de procedimento",
     "Procedimento código 309 = 'Paciente com 3 anos OU MAIS'. Marcado CORTESIA. Conferir cadastro."),
    ("4. Gabriela Castro Silva — 3 leads duplicados no Kommo",
     "Leads 11569512 (Closed-lost), 21768459 (Closed-won, ativo), 15036913 (Closed-lost). Sugere dedup."),
    ("5. 2 confirmados ainda não chegaram (17:00 Milza · 17:30 Dominicky)",
     "Recomenda ligação de confirmação de comparecimento."),
]

LEGENDA = (
    "<b>⚭</b> Lead conjunto (família 2+ pacientes no mesmo lead Kommo) · "
    "<b>⚠</b> Atenção · "
    "<b>✓</b> Realizado · "
    "<b>●</b> Em atendimento · "
    "<b>◐</b> Confirmado · "
    "<b>○</b> Agendado pendente"
)


# ============================================================
# PDF
# ============================================================

def gerar_pdf():
    doc = SimpleDocTemplate(
        OUTPUT,
        pagesize=landscape(A4),
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title="Relatório Consultas 16/06/2026 — Blink Oftalmologia",
        author="Blink Oftalmologia · Cowork/Claude",
    )

    styles = getSampleStyleSheet()

    style_titulo = ParagraphStyle(
        "Titulo", parent=styles["Title"],
        fontSize=15, leading=18, alignment=0,
        textColor=colors.HexColor("#1F4E79"),
        spaceAfter=2,
    )
    style_subtitulo = ParagraphStyle(
        "Subtitulo", parent=styles["Normal"],
        fontSize=11, leading=14, textColor=colors.HexColor("#444444"),
        spaceAfter=2,
    )
    style_obs = ParagraphStyle(
        "Obs", parent=styles["Normal"],
        fontSize=8, leading=10, textColor=colors.HexColor("#777777"),
        spaceAfter=8,
    )
    style_secao = ParagraphStyle(
        "Secao", parent=styles["Heading2"],
        fontSize=12, leading=14, textColor=colors.HexColor("#1F4E79"),
        spaceBefore=8, spaceAfter=4,
    )
    style_alerta_titulo = ParagraphStyle(
        "AlertaTitulo", parent=styles["Normal"],
        fontSize=9.5, leading=12, fontName="Helvetica-Bold",
        textColor=colors.HexColor("#A82A1F"),
        spaceAfter=1,
    )
    style_alerta_corpo = ParagraphStyle(
        "AlertaCorpo", parent=styles["Normal"],
        fontSize=9, leading=11, textColor=colors.HexColor("#333333"),
        leftIndent=12, spaceAfter=6,
    )
    style_legenda = ParagraphStyle(
        "Legenda", parent=styles["Normal"],
        fontSize=8, leading=10, textColor=colors.HexColor("#666666"),
        spaceBefore=4,
    )

    story = []

    # ----- Cabeçalho -----
    story.append(Paragraph(CABECALHO_TITULO, style_titulo))
    story.append(Paragraph(CABECALHO_SUBTITULO, style_subtitulo))
    story.append(Paragraph(GERADO_EM, style_obs))

    # ----- Resumo (mini tabela 2 colunas) -----
    resumo_data = [["Indicador", "Valor"]]
    for k, v in RESUMO:
        resumo_data.append([k, v])

    resumo_tbl = Table(resumo_data, colWidths=[68 * mm, 30 * mm])
    resumo_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F6FA")]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CCCCCC")),
    ]))
    story.append(resumo_tbl)
    story.append(Spacer(1, 6 * mm))

    # ----- Tabela principal -----
    story.append(Paragraph("Agendamentos (ordenado por horário)", style_secao))

    cabecalho_tab = ["Hora", "Paciente", "Idade", "Plano", "Status Medware", "Etapa Kommo", "Lead Kommo"]
    tabela_data = [cabecalho_tab] + [list(linha) for linha in LINHAS]

    # Largura total disponível em landscape A4 = 267mm com margens 15/15 = ~267mm
    col_widths = [
        16 * mm,   # Hora
        70 * mm,   # Paciente
        16 * mm,   # Idade
        38 * mm,   # Plano
        38 * mm,   # Status Medware
        38 * mm,   # Etapa Kommo
        30 * mm,   # Lead ID
    ]

    tabela_principal = Table(tabela_data, colWidths=col_widths, repeatRows=1)

    # Cores condicionais por status (linha)
    base_style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTSIZE", (0, 1), (-1, -1), 8.5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CCCCCC")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F9FB")]),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),    # Hora centralizada
        ("ALIGN", (2, 0), (2, -1), "CENTER"),    # Idade centralizada
        ("ALIGN", (6, 0), (6, -1), "CENTER"),    # Lead ID centralizada
    ]

    # Destacar linhas com alertas
    for idx, linha in enumerate(LINHAS, start=1):
        status_med = linha[4]
        etapa_kommo = linha[5]
        if "Realizado" in status_med and "5-Agendado" in etapa_kommo:
            # Discrepância Medware vs Kommo — amarelo claro
            base_style.append(("BACKGROUND", (0, idx), (-1, idx), colors.HexColor("#FFF8DC")))
        elif "Sem Kommo" in etapa_kommo:
            base_style.append(("BACKGROUND", (0, idx), (-1, idx), colors.HexColor("#FFE8E8")))
        elif "Agendado" in status_med and "Realizado" not in status_med:
            base_style.append(("BACKGROUND", (0, idx), (-1, idx), colors.HexColor("#FFF3DC")))

    tabela_principal.setStyle(TableStyle(base_style))
    story.append(tabela_principal)
    story.append(Paragraph(LEGENDA, style_legenda))

    # ----- Alertas críticos -----
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph("Alertas críticos", style_secao))
    for titulo, corpo in ALERTAS:
        story.append(Paragraph(titulo, style_alerta_titulo))
        story.append(Paragraph(corpo, style_alerta_corpo))

    # ----- Rodapé / nota final -----
    story.append(Spacer(1, 4 * mm))
    rodape = (
        "<b>Próxima ação sugerida:</b> sincronizar etapas Kommo dos 2 leads em discrepância (Ryan/Iara + "
        "Mariana) com status_id 91486864 (8-REALIZADO CONSULTA). Cadastrar lead Kommo para Milza de Castro "
        "Santana. Conferir procedimento de Bento Caetano (5 meses)."
    )
    story.append(Paragraph(rodape, style_obs))

    doc.build(story)
    print(f"PDF gerado: {OUTPUT}")


if __name__ == "__main__":
    gerar_pdf()
