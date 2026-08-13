"""
Gerador de PDF (DANFSE) a partir de XMLs da NFS-e Nacional
"""
import io
import logging
from lxml import etree
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

from api.retencoes import extrair_retencoes, descricao_retencao_iss

logger = logging.getLogger(__name__)

# Largura útil da página A4 com margens de 15mm
PAGE_WIDTH = A4[0] - 30 * mm


def _get_text(root, xpath):
    """Extrai texto de elemento XML ignorando namespaces"""
    parts = [p for p in xpath.split('//') if p and p != '.']
    
    if len(parts) > 1:
        parent_tag = parts[0].lower()
        child_tag = parts[-1].lower()
        
        for el in root.iter():
            local = el.tag.split('}')[-1] if '}' in el.tag else el.tag
            if local.lower() == parent_tag:
                for child in el.iter():
                    child_local = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                    if child_local.lower() == child_tag and child.text:
                        return child.text.strip()
    else:
        tag = parts[0].lower()
        for el in root.iter():
            local = el.tag.split('}')[-1] if '}' in el.tag else el.tag
            if local.lower() == tag and el.text:
                return el.text.strip()
    return None


def _fmt_cnpj(cnpj):
    """Formata CNPJ: 12345678000199 -> 12.345.678/0001-99"""
    if not cnpj or len(cnpj) < 14:
        return cnpj or ''
    c = cnpj.strip()
    if len(c) == 14:
        return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"
    if len(c) == 11:  # CPF
        return f"{c[:3]}.{c[3:6]}.{c[6:9]}-{c[9:]}"
    return c


def _fmt_valor(valor_str):
    """Formata valor: 1234.56 -> R$ 1.234,56"""
    if not valor_str:
        return 'R$ 0,00'
    try:
        v = float(valor_str)
        return f"R$ {v:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    except ValueError:
        return f"R$ {valor_str}"


def _fmt_data(data_str):
    """Formata data ISO para dd/mm/aaaa"""
    if not data_str:
        return ''
    try:
        # Suporta 2026-02-25T16:04:50-03:00 e 2026-02-25
        d = data_str[:10]
        parts = d.split('-')
        return f"{parts[2]}/{parts[1]}/{parts[0]}"
    except (IndexError, ValueError):
        return data_str


def _extrair_dados_xml(xml_content):
    """Extrai todos os dados relevantes do XML para o PDF"""
    root = etree.fromstring(xml_content.encode('utf-8'))
    
    dados = {}
    
    # NFS-e
    dados['nNFSe'] = _get_text(root, './/nNFSe') or ''
    dados['nDPS'] = _get_text(root, './/nDPS') or ''
    dados['serie'] = _get_text(root, './/serie') or ''
    dados['nDFSe'] = _get_text(root, './/nDFSe') or ''
    
    # Chave de acesso
    for el in root.iter():
        local = el.tag.split('}')[-1] if '}' in el.tag else el.tag
        if local.lower() == 'infnfse':
            chave = el.get('Id', '')
            # Remover prefixo NFS/NFSe
            for prefix in ['NFSe', 'NFS']:
                if chave.startswith(prefix):
                    chave = chave[len(prefix):]
            dados['chave_acesso'] = chave
            break
    
    # Datas
    dados['data_emissao'] = _fmt_data(
        _get_text(root, './/dhEmi') or _get_text(root, './/dtEmi')
    )
    dados['data_competencia'] = _fmt_data(_get_text(root, './/dCompet'))
    dados['data_processamento'] = _fmt_data(_get_text(root, './/dhProc'))
    
    # Emitente/Prestador
    dados['emit_cnpj'] = _fmt_cnpj(_get_text(root, './/emit//CNPJ'))
    dados['emit_nome'] = _get_text(root, './/emit//xNome') or ''
    dados['emit_logradouro'] = _get_text(root, './/emit//xLgr') or ''
    dados['emit_numero'] = _get_text(root, './/emit//nro') or ''
    dados['emit_bairro'] = _get_text(root, './/emit//xBairro') or ''
    dados['emit_cep'] = _get_text(root, './/emit//CEP') or ''
    dados['emit_uf'] = _get_text(root, './/emit//UF') or ''
    dados['emit_fone'] = _get_text(root, './/emit//fone') or ''
    
    # Município
    dados['municipio'] = _get_text(root, './/xLocEmi') or ''
    dados['local_prestacao'] = _get_text(root, './/xLocPrestacao') or ''
    
    # Tomador
    dados['toma_cnpj'] = _fmt_cnpj(
        _get_text(root, './/toma//CNPJ') or _get_text(root, './/toma//CPF')
    )
    dados['toma_nome'] = _get_text(root, './/toma//xNome') or ''
    
    # Valores
    dados['valor_servicos'] = _get_text(root, './/vServ') or _get_text(root, './/vLiq') or '0.00'
    dados['valor_liquido'] = _get_text(root, './/vLiq') or dados['valor_servicos']
    
    # Tributos
    dados['trib_nac'] = _get_text(root, './/cTribNac') or ''
    dados['trib_nac_desc'] = _get_text(root, './/xTribNac') or ''
    dados['trib_mun'] = _get_text(root, './/cTribMun') or ''
    dados['trib_mun_desc'] = _get_text(root, './/xTribMun') or ''
    
    # Descrição do serviço
    dados['descricao'] = _get_text(root, './/xDescServ') or \
                         _get_text(root, './/Discriminacao') or ''
    
    # Retenções de impostos (ver api/retencoes.py: o ISS retido não tem tag própria,
    # é o vISSQN quando a flag tpRetISSQN indica retenção)
    ret = extrair_retencoes(root)
    dados['ret_iss'] = str(ret['iss'])
    dados['ret_pis'] = str(ret['pis'])
    dados['ret_cofins'] = str(ret['cofins'])
    dados['ret_irrf'] = str(ret['irrf'])
    dados['ret_inss'] = str(ret['inss'])
    dados['ret_csll'] = str(ret['csll'])
    dados['ret_total'] = str(ret['total'])
    dados['iss_retido'] = ret['iss_retido']
    dados['ret_iss_desc'] = descricao_retencao_iss(ret['tp_ret_iss'])
    
    # ISS (valor calculado, não retido)
    dados['valor_iss'] = _get_text(root, './/vISSQN') or _get_text(root, './/vISS') or ''
    dados['aliq_iss'] = _get_text(root, './/pAliq') or ''
    
    # Aliquota total SN
    dados['aliq_total_sn'] = _get_text(root, './/pTotTribSN') or ''
    
    # Ambiente
    tp_amb = _get_text(root, './/tpAmb')
    dados['ambiente'] = 'PRODUÇÃO' if tp_amb == '1' else 'HOMOLOGAÇÃO'
    
    # Status
    c_stat = _get_text(root, './/cStat')
    dados['status'] = 'Autorizada' if c_stat == '100' else f'Status {c_stat}'
    
    return dados


def gerar_pdf_nfse(xml_content):
    """
    Gera um PDF (DANFSE) a partir do conteúdo XML de uma NFS-e.
    
    Args:
        xml_content: String com o conteúdo XML
    
    Returns:
        bytes com o PDF gerado
    """
    dados = _extrair_dados_xml(xml_content)
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm
    )
    
    # Estilos
    styles = getSampleStyleSheet()
    
    style_titulo = ParagraphStyle(
        'Titulo', parent=styles['Heading1'],
        fontSize=14, alignment=TA_CENTER,
        spaceAfter=2 * mm, textColor=colors.HexColor('#1a5276')
    )
    style_subtitulo = ParagraphStyle(
        'Subtitulo', parent=styles['Normal'],
        fontSize=9, alignment=TA_CENTER,
        spaceAfter=4 * mm, textColor=colors.HexColor('#666666')
    )
    style_secao = ParagraphStyle(
        'Secao', parent=styles['Heading3'],
        fontSize=10, spaceBefore=4 * mm, spaceAfter=2 * mm,
        textColor=colors.HexColor('#2c3e50'),
        borderPadding=(0, 0, 2, 0)
    )
    style_normal = ParagraphStyle(
        'Info', parent=styles['Normal'],
        fontSize=9, leading=13
    )
    style_label = ParagraphStyle(
        'Label', parent=styles['Normal'],
        fontSize=7.5, textColor=colors.HexColor('#888888'), leading=10
    )
    style_valor = ParagraphStyle(
        'Valor', parent=styles['Normal'],
        fontSize=9, leading=12
    )
    style_valor_grande = ParagraphStyle(
        'ValorGrande', parent=styles['Normal'],
        fontSize=12, alignment=TA_RIGHT,
        textColor=colors.HexColor('#1a5276'), leading=16
    )
    style_chave = ParagraphStyle(
        'Chave', parent=styles['Normal'],
        fontSize=7, alignment=TA_CENTER,
        textColor=colors.HexColor('#555555'), leading=10
    )
    style_descricao = ParagraphStyle(
        'Descricao', parent=styles['Normal'],
        fontSize=9, leading=13, spaceBefore=2 * mm
    )
    
    elements = []
    
    # --- Cabeçalho ---
    elements.append(Paragraph("DOCUMENTO AUXILIAR DA NFS-e", style_titulo))
    elements.append(Paragraph("Nota Fiscal de Serviço Eletrônica — Padrão Nacional", style_subtitulo))
    
    # --- Dados da NFS-e (grid) ---
    def campo(label, valor):
        """Cria célula com label + valor empilhados"""
        return [Paragraph(label, style_label), Paragraph(str(valor), style_valor)]
    
    # Linha 1: Números
    grid_numeros = Table(
        [[
            campo("Nº NFS-e", dados['nNFSe']),
            campo("Nº DPS", dados['nDPS']),
            campo("Série", dados['serie']),
            campo("Nº DFSe", dados['nDFSe']),
        ]],
        colWidths=[PAGE_WIDTH * 0.25] * 4,
        style=TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 2 * mm),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2 * mm),
            ('LEFTPADDING', (0, 0), (-1, -1), 2 * mm),
        ])
    )
    elements.append(grid_numeros)
    
    # Linha 2: Datas e Status
    grid_datas = Table(
        [[
            campo("Data de Emissão", dados['data_emissao']),
            campo("Competência", dados['data_competencia']),
            campo("Status", dados['status']),
            campo("Município", dados['municipio']),
        ]],
        colWidths=[PAGE_WIDTH * 0.25] * 4,
        style=TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 2 * mm),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2 * mm),
            ('LEFTPADDING', (0, 0), (-1, -1), 2 * mm),
        ])
    )
    elements.append(grid_datas)
    
    elements.append(Spacer(1, 3 * mm))
    
    # --- Prestador ---
    elements.append(Paragraph("PRESTADOR DE SERVIÇOS", style_secao))
    
    endereco = f"{dados['emit_logradouro']}, {dados['emit_numero']}" if dados['emit_logradouro'] else ''
    if dados['emit_bairro']:
        endereco += f" — {dados['emit_bairro']}"
    if dados['emit_cep']:
        cep = dados['emit_cep']
        if len(cep) == 8:
            cep = f"{cep[:5]}-{cep[5:]}"
        endereco += f" — CEP: {cep}"
    
    grid_prestador = Table(
        [
            [campo("CNPJ", dados['emit_cnpj']), campo("Razão Social", dados['emit_nome'])],
            [campo("Endereço", endereco), campo("Telefone", dados['emit_fone'])],
        ],
        colWidths=[PAGE_WIDTH * 0.35, PAGE_WIDTH * 0.65],
        style=TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 2 * mm),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2 * mm),
            ('LEFTPADDING', (0, 0), (-1, -1), 2 * mm),
        ])
    )
    elements.append(grid_prestador)
    
    elements.append(Spacer(1, 3 * mm))
    
    # --- Tomador ---
    elements.append(Paragraph("TOMADOR DE SERVIÇOS", style_secao))
    
    grid_tomador = Table(
        [[campo("CNPJ/CPF", dados['toma_cnpj']), campo("Nome/Razão Social", dados['toma_nome'])]],
        colWidths=[PAGE_WIDTH * 0.35, PAGE_WIDTH * 0.65],
        style=TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 2 * mm),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2 * mm),
            ('LEFTPADDING', (0, 0), (-1, -1), 2 * mm),
        ])
    )
    elements.append(grid_tomador)
    
    elements.append(Spacer(1, 3 * mm))
    
    # --- Serviço ---
    elements.append(Paragraph("DESCRIÇÃO DO SERVIÇO", style_secao))
    
    grid_servico = Table(
        [
            [
                campo("Código Trib. Nacional", f"{dados['trib_nac']}"),
                campo("Descrição Trib. Nacional", dados['trib_nac_desc']),
            ],
            [
                campo("Código Trib. Municipal", f"{dados['trib_mun']}"),
                campo("Descrição Trib. Municipal", dados['trib_mun_desc']),
            ],
        ],
        colWidths=[PAGE_WIDTH * 0.25, PAGE_WIDTH * 0.75],
        style=TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 2 * mm),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2 * mm),
            ('LEFTPADDING', (0, 0), (-1, -1), 2 * mm),
        ])
    )
    elements.append(grid_servico)
    
    # Descrição
    elements.append(Paragraph(dados['descricao'], style_descricao))
    
    elements.append(Spacer(1, 3 * mm))
    
    # --- Valores ---
    elements.append(Paragraph("VALORES", style_secao))
    
    grid_valores = Table(
        [[
            campo("Valor dos Serviços", _fmt_valor(dados['valor_servicos'])),
            campo(
                "ISS (RETIDO)" if dados['iss_retido'] else "ISS",
                _fmt_valor(dados['valor_iss']) if dados['valor_iss'] else '-'
            ),
            [
                Paragraph("VALOR LÍQUIDO", style_label),
                Paragraph(f"<b>{_fmt_valor(dados['valor_liquido'])}</b>", style_valor_grande)
            ],
        ]],
        colWidths=[PAGE_WIDTH * 0.33, PAGE_WIDTH * 0.33, PAGE_WIDTH * 0.34],
        style=TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 2 * mm),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3 * mm),
            ('LEFTPADDING', (0, 0), (-1, -1), 2 * mm),
            ('BACKGROUND', (2, 0), (2, 0), colors.HexColor('#eaf2f8')),
        ])
    )
    elements.append(grid_valores)
    
    # --- Retenções (só mostra se houver pelo menos uma) ---
    retencoes = {
        'ISS Retido': dados.get('ret_iss', ''),
        'PIS': dados.get('ret_pis', ''),
        'COFINS': dados.get('ret_cofins', ''),
        'IRRF': dados.get('ret_irrf', ''),
        'INSS/CP': dados.get('ret_inss', ''),
        'CSLL': dados.get('ret_csll', ''),
    }
    
    def _positivo(valor):
        """Valores vêm como texto de Decimal ('0' quando não há retenção)"""
        try:
            return float(valor or 0) > 0
        except ValueError:
            return False

    # Filtrar apenas os que têm valor
    ret_com_valor = {k: v for k, v in retencoes.items() if _positivo(v)}

    if ret_com_valor:
        elements.append(Spacer(1, 3 * mm))
        elements.append(Paragraph("RETENÇÕES", style_secao))

        # Quem reteve o ISS (tomador ou intermediário), quando houver
        label_iss = "ISS Retido"
        if dados.get('ret_iss_desc'):
            label_iss = f"ISS Retido — {dados['ret_iss_desc']}"

        def campo_ret(label, chave):
            valor = retencoes[chave]
            return campo(label, _fmt_valor(valor) if _positivo(valor) else '-')

        # Linha 1: ISS, PIS, COFINS
        row1 = [
            campo_ret(label_iss, 'ISS Retido'),
            campo_ret("PIS", 'PIS'),
            campo_ret("COFINS", 'COFINS'),
        ]
        # Linha 2: IRRF, INSS, CSLL
        row2 = [
            campo_ret("IRRF", 'IRRF'),
            campo_ret("INSS/CP", 'INSS/CP'),
            campo_ret("CSLL", 'CSLL'),
        ]

        grid_retencoes = Table(
            [row1, row2],
            colWidths=[PAGE_WIDTH * 0.333] * 3,
            style=TableStyle([
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('TOPPADDING', (0, 0), (-1, -1), 2 * mm),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2 * mm),
                ('LEFTPADDING', (0, 0), (-1, -1), 2 * mm),
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fef9e7')),
            ])
        )
        elements.append(grid_retencoes)

        # Total retido — fecha a conta com o valor líquido
        grid_total_ret = Table(
            [[
                Paragraph("TOTAL DAS RETENÇÕES", style_label),
                Paragraph(f"<b>{_fmt_valor(dados['ret_total'])}</b>", style_valor),
            ]],
            colWidths=[PAGE_WIDTH * 0.666, PAGE_WIDTH * 0.334],
            style=TableStyle([
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
                ('TOPPADDING', (0, 0), (-1, -1), 1.5 * mm),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 1.5 * mm),
                ('LEFTPADDING', (0, 0), (-1, -1), 2 * mm),
                ('RIGHTPADDING', (0, 0), (-1, -1), 2 * mm),
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fcf3cf')),
            ])
        )
        elements.append(grid_total_ret)

    # Alíquota SN
    if dados.get('aliq_total_sn'):
        elements.append(Spacer(1, 2 * mm))
        elements.append(Paragraph(
            f"<i>Alíquota total Simples Nacional: {dados['aliq_total_sn']}%</i>",
            style_label
        ))
    
    elements.append(Spacer(1, 5 * mm))
    
    # --- Chave de acesso ---
    chave = dados.get('chave_acesso', '')
    if chave:
        # Formatar chave em grupos de 4
        chave_fmt = ' '.join([chave[i:i+4] for i in range(0, len(chave), 4)])
        elements.append(Paragraph(f"<b>Chave de Acesso:</b> {chave_fmt}", style_chave))
    
    elements.append(Spacer(1, 3 * mm))
    elements.append(Paragraph(
        "Documento gerado automaticamente a partir do XML da NFS-e — Padrão Nacional",
        ParagraphStyle('Rodape', parent=styles['Normal'], fontSize=7,
                       alignment=TA_CENTER, textColor=colors.HexColor('#aaaaaa'))
    ))
    
    # Build
    doc.build(elements)
    return buffer.getvalue()
