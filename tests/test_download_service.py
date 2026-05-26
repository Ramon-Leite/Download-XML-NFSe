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
def service():
    """DownloadService com dependências mockadas"""
    with patch('services.download_service.NFSeRepository') as mock_nfse_repo, \
         patch('services.download_service.EmpresaRepository') as mock_emp_repo, \
         patch('services.download_service.CertificateManager') as mock_cert, \
         patch('services.download_service.XMLParser') as mock_parser:
        
        svc = DownloadService()
        # Os mocks já foram injetados pelo patch no __init__
        yield svc


def _make_doc(nsu, tipo_doc='NFSE', xml_base64=None):
    """Helper para criar um documento mock da API"""
    return {
        'NSU': nsu,
        'TipoDocumento': tipo_doc,
        'ArquivoXml': xml_base64 or 'dGVzdGU='  # base64 de 'teste'
    }


class TestDownloadNFSe:
    """Testes para o método download_nfse"""
    
    def test_download_com_notas_novas(self, service, empresa):
        """Deve baixar e contabilizar notas novas corretamente"""
        # Configurar mocks
        service.cert_manager.convert_pfx_to_pem.return_value = ('/tmp/cert.pem', '/tmp/key.pem')
        
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        
        # API retorna 1 documento
        mock_client.buscar_documentos_desde_nsu.return_value = [_make_doc(101)]
        mock_client.extrair_xml_documento.return_value = '<xml>conteudo</xml>'
        
        # Parser retorna dados válidos
        service.xml_parser.parse_nfse.return_value = {
            'chave_acesso': 'CHAVE_001',
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
        
        # Nota não existe no banco
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
    
    def test_download_nota_duplicada(self, service, empresa):
        """Deve contabilizar duplicatas sem salvar novamente"""
        service.cert_manager.convert_pfx_to_pem.return_value = ('/tmp/cert.pem', '/tmp/key.pem')
        
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.buscar_documentos_desde_nsu.return_value = [_make_doc(101)]
        mock_client.extrair_xml_documento.return_value = '<xml>conteudo</xml>'
        
        service.xml_parser.parse_nfse.return_value = {
            'chave_acesso': 'CHAVE_DUP',
            'numero': '002',
            'data_emissao': date(2026, 2, 15),
            'prestador_cnpj': '12345678000199',
            'tomador_cnpj': '99999999000199',
            'is_evento': False
        }
        
        # Nota JÁ existe
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
        # Não deve ter chamado create
        service.nfse_repository.create.assert_not_called()
    
    def test_download_evento_cancelamento(self, service, empresa):
        """Deve processar evento de cancelamento e atualizar nota no banco"""
        service.cert_manager.convert_pfx_to_pem.return_value = ('/tmp/cert.pem', '/tmp/key.pem')
        
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.buscar_documentos_desde_nsu.return_value = [_make_doc(102, 'EVENTO')]
        mock_client.extrair_xml_documento.return_value = '<xml>evento</xml>'
        
        service.xml_parser.parse_nfse.return_value = {
            'is_evento': True,
            'chave_acesso': 'CHAVE_CANCEL',
            'status': 'CANCELADA'
        }
        
        # Nota existe com status NORMAL
        nota_existente = NFSe(
            id=10,
            empresa_id=1,
            chave_acesso='CHAVE_CANCEL',
            status='NORMAL',
            xml_path=None
        )
        service.nfse_repository.get_by_chave.return_value = nota_existente
        
        with patch('services.download_service.NFSeClient', return_value=mock_client):
            stats = service.download_nfse(
                empresa=empresa,
                tipo='AMBAS',
                data_inicio=date(2026, 2, 1),
                data_fim=date(2026, 2, 28)
            )
        
        # Deve ter atualizado o status
        service.nfse_repository.update.assert_called_once()
        nota_atualizada = service.nfse_repository.update.call_args[0][0]
        assert nota_atualizada.status == 'CANCELADA'
    
    def test_download_atualiza_ultimo_nsu(self, service, empresa):
        """Deve atualizar o ultimo_nsu da empresa após download"""
        service.cert_manager.convert_pfx_to_pem.return_value = ('/tmp/cert.pem', '/tmp/key.pem')
        
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.buscar_documentos_desde_nsu.return_value = [
            _make_doc(150),
            _make_doc(200)
        ]
        mock_client.extrair_xml_documento.return_value = '<xml>conteudo</xml>'
        
        service.xml_parser.parse_nfse.return_value = {
            'chave_acesso': 'CHAVE_NSU',
            'numero': '003',
            'data_emissao': date(2026, 2, 15),
            'prestador_cnpj': '12345678000199',
            'tomador_cnpj': '99999999000199',
            'is_evento': False
        }
        service.nfse_repository.exists_by_chave.return_value = False
        
        with patch('services.download_service.NFSeClient', return_value=mock_client):
            service.download_nfse(
                empresa=empresa,
                tipo='EMITIDA',
                data_inicio=date(2026, 2, 1),
                data_fim=date(2026, 2, 28)
            )
        
        # ultimo_nsu deve ter sido atualizado para 200 (o maior)
        service.empresa_repository.update.assert_called_once()
        assert empresa.ultimo_nsu == 200
    
    def test_download_nenhum_documento(self, service, empresa):
        """Deve retornar stats zerados quando não há documentos"""
        service.cert_manager.convert_pfx_to_pem.return_value = ('/tmp/cert.pem', '/tmp/key.pem')
        
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.buscar_documentos_desde_nsu.return_value = []
        
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
        
        # Não deve ter chamado a API de eventos
        mock_client.buscar_eventos_nfse.assert_not_called()
        assert stats['atualizadas'] == 0
