"""
Extração de impostos retidos da NFS-e Nacional.

Módulo compartilhado entre o gerador de PDF (services/pdf_service.py) e o parser
que alimenta o banco (api/xml_parser.py), para que a tela e o DANFSE nunca
divirjam sobre o que está retido.

PONTO IMPORTANTE DO LAYOUT NACIONAL: não existe tag "vRetISSQN"/"vISSRet".
O ISS é sempre informado em <vISSQN> (dentro de infNFSe/valores) e o que diz se
ele foi retido é a flag <tpRetISSQN>, lá no DPS:

    tpRetISSQN     1 = Não Retido | 2 = Retido pelo Tomador | 3 = Retido pelo Intermediário
    tpRetPisCofins 1 = Retido     | 2 = Não Retido          | 0/3 = não retido/não informado

PIS e COFINS seguem a mesma ideia: <vPis>/<vCofins> trazem o valor calculado,
que só é retenção quando tpRetPisCofins == 1. Já vRetIRRF, vRetCSLL e vRetCP
(INSS/Contribuição Previdenciária) só existem quando há retenção, então valem
pelo próprio valor.

Regra validada contra o <vTotalRet> declarado pelos emissores nos XMLs baixados:
228 de 235 notas batem exatamente. As 7 restantes são erro do emissor — marcam
tpRetISSQN=1 (não retido) e não reduzem o vLiq, mas ainda assim somam o ISS no
vTotalRet. Nesses casos a flag e o vLiq concordam entre si, então a flag manda.
"""
from decimal import Decimal, InvalidOperation

# Códigos de tpRetISSQN que significam ISS retido (2 = tomador, 3 = intermediário)
_ISS_RETIDO = ('2', '3')
# Único código de tpRetPisCofins que significa PIS/COFINS retido
_PIS_COFINS_RETIDO = '1'


def _local_name(el):
    """Nome da tag sem o namespace"""
    return el.tag.split('}')[-1] if '}' in str(el.tag) else str(el.tag)


def _texto(root, tag):
    """Primeiro elemento com esse nome local, ignorando namespace"""
    alvo = tag.lower()
    for el in root.iter():
        if _local_name(el).lower() == alvo and el.text:
            return el.text.strip()
    return None


def _decimal(valor):
    """Converte texto para Decimal, devolvendo 0 quando ausente ou inválido"""
    if not valor:
        return Decimal('0')
    try:
        return Decimal(str(valor).replace(',', '.'))
    except (InvalidOperation, ValueError):
        return Decimal('0')


def extrair_retencoes(root):
    """
    Lê as retenções de uma NFS-e já parseada (elemento raiz do lxml).

    Returns:
        dict com Decimals 'iss', 'pis', 'cofins', 'irrf', 'csll', 'inss' e 'total',
        além de 'iss_retido' (bool) e 'tp_ret_iss' (código bruto, para exibição).
    """
    tp_ret_iss = _texto(root, 'tpRetISSQN')
    tp_ret_pis_cofins = _texto(root, 'tpRetPisCofins')

    iss_retido = tp_ret_iss in _ISS_RETIDO
    pis_cofins_retido = tp_ret_pis_cofins == _PIS_COFINS_RETIDO

    ret = {
        'iss': _decimal(_texto(root, 'vISSQN')) if iss_retido else Decimal('0'),
        'pis': _decimal(_texto(root, 'vPis')) if pis_cofins_retido else Decimal('0'),
        'cofins': _decimal(_texto(root, 'vCofins')) if pis_cofins_retido else Decimal('0'),
        'irrf': _decimal(_texto(root, 'vRetIRRF')),
        'csll': _decimal(_texto(root, 'vRetCSLL')),
        'inss': _decimal(_texto(root, 'vRetCP')),
    }

    ret['total'] = sum(ret.values(), Decimal('0'))
    ret['iss_retido'] = iss_retido
    ret['tp_ret_iss'] = tp_ret_iss
    return ret


def descricao_retencao_iss(tp_ret_iss):
    """Texto curto de quem reteve o ISS, para o DANFSE"""
    return {
        '2': 'Retido pelo Tomador',
        '3': 'Retido pelo Intermediário',
    }.get(tp_ret_iss, '')
