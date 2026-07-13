"""
Testes unitários para DownloadService
"""
import pytest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.models import Empresa, NFSe
from services.download_service import DownloadService


@pytest.fixture
def empresa():
    """Empresa de exemplo para testes"""
    return Empresa(
        id=1,
        cnpj="12345678000199",
        razao_social="Empresa Teste LTDA",
        certificado_path="/path/to/cert.pfx",
        certificado_senha="senha123",
        ultimo_nsu=100,
        ativo=True
    )


@pytest.fixture
def service(tmp_path):
    """DownloadService com dependências mockadas e XMLs em diretório temporário"""
    with patch('services.download_service.NFSeRepository') as mock_nfse_repo, \
         patch('services.download_service.EmpresaRepository') as mock_emp_repo, \
         patch('services.download_service.EventoPendenteRepository') as mock_ev_repo, \
         patch('services.download_service.SchedulerConfigRepository') as mock_sched, \
         patch('services.download_service.CertificateManager') as mock_cert, \
         patch('services.download_service.XMLParser') as mock_parser, \
         patch('services.download_service.config.XMLS_DIR', tmp_path):

        # Sem diretório customizado de XMLs
        mock_sched.return_value.get.return_value = None

        svc = DownloadService()
        # Sem eventos pendentes por padrão
        svc.evento_pendente_repository.get_by_chave.return_value = []
        yield svc


def _make_doc(nsu, tipo_doc='NFSE', xml_base64=None):
    """Helper para criar um documento mock da API"""
    return {
        'NSU': nsu,
        'TipoDocumento': tipo_doc,
        'ArquivoXml': xml_base64 or 'dGVzdGU='  # base64 de 'teste'
    }


def _make_client(lotes):
    """Helper para criar um NFSeClient mock que itera sobre lotes"""
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.iterar_lotes_dfe.return_value = iter(lotes)
    mock_client.extrair_xml_documento.return_value = '<xml>conteudo</xml>'
    return mock_client


def _parsed_nfse(chave='CHAVE_001', **overrides):
    """Helper para um resultado de parse válido"""
    data = {
        'chave_acesso': chave,
        'numero': '001',
        'data_emissao': date(2026, 2, 15),
        'data_competencia': date(2026, 2, 1),
        'prestador_cnpj': '12345678000199',
        'prestador_nome': 'Empresa Teste',
        'tomador_cnpj': '99999999000199',
        'tomador_nome': 'Tomador Teste',
        'valor_servicos': Decimal('1000.00'),
        'valor_iss': Decimal('50.00'),
        'codigo_servico': '1.01',
        'descricao_servico': 'Teste',
        'status': 'NORMAL',
        'is_evento': False
    }
    data.update(overrides)
    return data


class TestDownloadNFSe:
    """Testes para o método download_nfse"""

    def test_download_com_notas_novas(self, service, empresa):
        """Deve baixar e contabilizar notas novas corretamente"""
        service.cert_manager.convert_pfx_to_pem.return_value = ('/tmp/cert.pem', '/tmp/key.pem')

        mock_client = _make_client([[_make_doc(101)]])
        service.xml_parser.parse_nfse.return_value = _parsed_nfse()
        service.nfse_repository.exists_by_chave.return_value = False

        with patch('services.download_service.NFSeClient', return_value=mock_client):
            stats = service.download_nfse(
                empresa=empresa,
                tipo='EMITIDA',
                data_inicio=date(2026, 2, 1),
                data_fim=date(2026, 2, 28)
            )

        assert stats['total_encontradas'] == 1
        assert stats['novas'] == 1
        assert stats['duplicadas'] == 0
        assert stats['erros'] == 0

    def test_nota_fora_do_periodo_e_salva(self, service, empresa):
        """
        REGRESSÃO (bug das notas sumidas): nota fora do período solicitado
        deve ser SALVA mesmo assim — o filtro é só estatístico.
        """
        service.cert_manager.convert_pfx_to_pem.return_value = ('/tmp/cert.pem', '/tmp/key.pem')

        mock_client = _make_client([[_make_doc(101)]])
        # Nota de JANEIRO, mas o download pede FEVEREIRO
        service.xml_parser.parse_nfse.return_value = _parsed_nfse(
            chave='CHAVE_FORA_PERIODO',
            data_emissao=date(2026, 1, 28),
            data_competencia=date(2026, 1, 1)
        )
        service.nfse_repository.exists_by_chave.return_value = False

        with patch('services.download_service.NFSeClient', return_value=mock_client):
            stats = service.download_nfse(
                empresa=empresa,
                tipo='AMBAS',
                data_inicio=date(2026, 2, 1),
                data_fim=date(2026, 2, 28)
            )

        # A nota FOI salva, e o usuário é informado de que caiu fora do período
        service.nfse_repository.create.assert_called_once()
        assert stats['novas'] == 1
        assert stats['novas_fora_periodo'] == 1

    def test_download_nota_duplicada(self, service, empresa):
        """Deve contabilizar duplicatas sem salvar novamente"""
        service.cert_manager.convert_pfx_to_pem.return_value = ('/tmp/cert.pem', '/tmp/key.pem')

        mock_client = _make_client([[_make_doc(101)]])
        service.xml_parser.parse_nfse.return_value = _parsed_nfse(chave='CHAVE_DUP')
        service.nfse_repository.exists_by_chave.return_value = True

        with patch('services.download_service.NFSeClient', return_value=mock_client):
            stats = service.download_nfse(
                empresa=empresa,
                tipo='EMITIDA',
                data_inicio=date(2026, 2, 1),
                data_fim=date(2026, 2, 28)
            )

        assert stats['duplicadas'] == 1
        assert stats['novas'] == 0
        service.nfse_repository.create.assert_not_called()
        # Dedupe deve ser POR EMPRESA
        service.nfse_repository.exists_by_chave.assert_called_with('CHAVE_DUP', empresa_id=empresa.id)

    def test_download_evento_cancelamento(self, service, empresa):
        """Deve processar evento de cancelamento e atualizar nota no banco"""
        service.cert_manager.convert_pfx_to_pem.return_value = ('/tmp/cert.pem', '/tmp/key.pem')

        mock_client = _make_client([[_make_doc(102, 'EVENTO')]])
        service.xml_parser.parse_nfse.return_value = {
            'is_evento': True,
            'chave_acesso': 'CHAVE_CANCEL',
            'status': 'CANCELADA'
        }

        nota_existente = NFSe(
            id=10,
            empresa_id=1,
            chave_acesso='CHAVE_CANCEL',
            status='NORMAL',
            xml_path=None
        )
        service.nfse_repository.get_all_by_chave.return_value = [nota_existente]

        with patch('services.download_service.NFSeClient', return_value=mock_client):
            stats = service.download_nfse(
                empresa=empresa,
                tipo='AMBAS',
                data_inicio=date(2026, 2, 1),
                data_fim=date(2026, 2, 28)
            )

        service.nfse_repository.update.assert_called_once()
        nota_atualizada = service.nfse_repository.update.call_args[0][0]
        assert nota_atualizada.status == 'CANCELADA'

    def test_evento_antes_da_nota_fica_pendente(self, service, empresa):
        """Evento cuja nota ainda não foi baixada deve ficar pendente"""
        service.cert_manager.convert_pfx_to_pem.return_value = ('/tmp/cert.pem', '/tmp/key.pem')

        mock_client = _make_client([[_make_doc(102, 'EVENTO')]])
        service.xml_parser.parse_nfse.return_value = {
            'is_evento': True,
            'chave_acesso': 'CHAVE_SEM_NOTA',
            'status': 'CANCELADA'
        }
        # Nenhuma nota com essa chave no banco
        service.nfse_repository.get_all_by_chave.return_value = []

        with patch('services.download_service.NFSeClient', return_value=mock_client):
            service.download_nfse(
                empresa=empresa,
                tipo='AMBAS',
                data_inicio=date(2026, 2, 1),
                data_fim=date(2026, 2, 28)
            )

        service.evento_pendente_repository.add.assert_called_once_with('CHAVE_SEM_NOTA', 'CANCELADA')
        service.nfse_repository.update.assert_not_called()

    def test_download_atualiza_ultimo_nsu(self, service, empresa):
        """Deve atualizar o ultimo_nsu da empresa após download"""
        service.cert_manager.convert_pfx_to_pem.return_value = ('/tmp/cert.pem', '/tmp/key.pem')

        mock_client = _make_client([[_make_doc(150), _make_doc(200)]])
        service.xml_parser.parse_nfse.side_effect = [
            _parsed_nfse(chave='CHAVE_NSU_150'),
            _parsed_nfse(chave='CHAVE_NSU_200'),
        ]
        service.nfse_repository.exists_by_chave.return_value = False

        with patch('services.download_service.NFSeClient', return_value=mock_client):
            service.download_nfse(
                empresa=empresa,
                tipo='EMITIDA',
                data_inicio=date(2026, 2, 1),
                data_fim=date(2026, 2, 28)
            )

        service.empresa_repository.update.assert_called_once()
        assert empresa.ultimo_nsu == 200

    def test_falha_transitoria_segura_ponteiro_nsu(self, service, empresa):
        """
        REGRESSÃO: falha transitória (ex.: banco travado) NÃO pode avançar
        o ponteiro NSU — o documento precisa ser reprocessado depois.
        """
        service.cert_manager.convert_pfx_to_pem.return_value = ('/tmp/cert.pem', '/tmp/key.pem')

        mock_client = _make_client([[_make_doc(150), _make_doc(200)]])
        service.xml_parser.parse_nfse.side_effect = [
            _parsed_nfse(chave='CHAVE_FALHA'),
            _parsed_nfse(chave='CHAVE_OK'),
        ]
        service.nfse_repository.exists_by_chave.return_value = False
        # O primeiro INSERT falha (transitório); o segundo funcionaria
        service.nfse_repository.create.side_effect = [Exception("database is locked"), 55]

        with patch('services.download_service.NFSeClient', return_value=mock_client):
            stats = service.download_nfse(
                empresa=empresa,
                tipo='AMBAS',
                data_inicio=date(2026, 2, 1),
                data_fim=date(2026, 2, 28)
            )

        # Ponteiro NÃO avançou: NSU 150 será re-baixado na próxima execução
        assert empresa.ultimo_nsu == 100
        service.empresa_repository.update.assert_not_called()
        assert stats['erros'] == 1

    def test_xml_invalido_vai_para_quarentena_e_nao_trava(self, service, empresa, tmp_path):
        """XML não parseável deve ir para quarentena sem travar o ponteiro"""
        service.cert_manager.convert_pfx_to_pem.return_value = ('/tmp/cert.pem', '/tmp/key.pem')

        mock_client = _make_client([[_make_doc(150)]])
        service.xml_parser.parse_nfse.return_value = None  # parse falhou

        with patch('services.download_service.NFSeClient', return_value=mock_client):
            stats = service.download_nfse(
                empresa=empresa,
                tipo='AMBAS',
                data_inicio=date(2026, 2, 1),
                data_fim=date(2026, 2, 28)
            )

        # Erro registrado, XML preservado, mas ponteiro avança (falha não é transitória)
        assert stats['erros'] == 1
        assert empresa.ultimo_nsu == 150
        quarentena = list((tmp_path / empresa.cnpj / 'quarentena').glob('*.xml'))
        assert len(quarentena) == 1

    def test_download_nenhum_documento(self, service, empresa):
        """Deve retornar stats zerados quando não há documentos"""
        service.cert_manager.convert_pfx_to_pem.return_value = ('/tmp/cert.pem', '/tmp/key.pem')

        mock_client = _make_client([])

        with patch('services.download_service.NFSeClient', return_value=mock_client):
            stats = service.download_nfse(
                empresa=empresa,
                tipo='AMBAS',
                data_inicio=date(2026, 2, 1),
                data_fim=date(2026, 2, 28)
            )

        assert stats['total_encontradas'] == 0
        assert stats['novas'] == 0
        assert stats['erros'] == 0

    def test_download_erro_certificado(self, service, empresa):
        """Deve retornar erro quando certificado falha"""
        service.cert_manager.convert_pfx_to_pem.side_effect = ValueError("Senha inválida")

        stats = service.download_nfse(
            empresa=empresa,
            tipo='AMBAS',
            data_inicio=date(2026, 2, 1),
            data_fim=date(2026, 2, 28)
        )

        assert stats['erros'] == 1
        assert len(stats['detalhes_erros']) == 1
        assert 'Senha inválida' in stats['detalhes_erros'][0]

    def test_cleanup_certificado_mesmo_com_erro(self, service, empresa):
        """PEMs temporários devem ser limpos mesmo quando o download falha"""
        service.cert_manager.convert_pfx_to_pem.side_effect = ValueError("Senha inválida")

        service.download_nfse(
            empresa=empresa,
            tipo='AMBAS',
            data_inicio=date(2026, 2, 1),
            data_fim=date(2026, 2, 28)
        )

        service.cert_manager.cleanup_temp_files.assert_called_once_with(empresa.cnpj)


class TestSincronizarStatus:
    """Testes para sincronizar_status_notas"""

    def test_pula_notas_ja_canceladas(self, service, empresa):
        """Deve pular notas que já não estão com status NORMAL"""
        service.cert_manager.convert_pfx_to_pem.return_value = ('/tmp/cert.pem', '/tmp/key.pem')

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        nota_cancelada = NFSe(id=1, chave_acesso='X', status='CANCELADA')

        with patch('services.download_service.NFSeClient', return_value=mock_client):
            stats = service.sincronizar_status_notas([nota_cancelada], empresa)

        mock_client.buscar_eventos_nfse.assert_not_called()
        assert stats['atualizadas'] == 0
