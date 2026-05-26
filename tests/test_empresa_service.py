"""
Testes unitários para EmpresaService
"""
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.models import Empresa
from services.empresa_service import EmpresaService


@pytest.fixture
def service():
    """EmpresaService com dependências mockadas"""
    with patch('services.empresa_service.EmpresaRepository') as mock_repo, \
         patch('services.empresa_service.CertificateManager') as mock_cert:
        
        svc = EmpresaService()
        yield svc


@pytest.fixture
def cert_info_valido():
    """Info de certificado válido"""
    return {
        'valid': True,
        'is_expired': False,
        'expiry_date': datetime(2027, 12, 31),
        'cnpj': '12345678000199',
        'subject_cn': 'Empresa Teste',
        'issuer': 'AC Teste',
        'serial_number': 123456
    }


class TestCadastrarEmpresa:
    """Testes para cadastrar_empresa"""
    
    def test_cadastro_sucesso(self, service, cert_info_valido):
        """Deve cadastrar empresa com certificado válido"""
        service.cert_manager.validate_certificate.return_value = cert_info_valido
        service.repository.get_by_cnpj.return_value = None  # Não existe
        service.repository.create.return_value = 1
        
        with patch('services.empresa_service.shutil.copy2'):
            resultado = service.cadastrar_empresa(
                cnpj="12345678000199",
                razao_social="Empresa Teste LTDA",
                nome_fantasia="Teste",
                certificado_path="/path/to/cert.pfx",
                certificado_senha="senha123"
            )
        
        assert resultado['success'] is True
        assert resultado['empresa_id'] == 1
        assert resultado['cert_info'] == cert_info_valido
        service.repository.create.assert_called_once()
    
    def test_rejeita_certificado_invalido(self, service):
        """Deve rejeitar empresa com certificado inválido"""
        service.cert_manager.validate_certificate.return_value = {
            'valid': False,
            'error': 'Senha incorreta'
        }
        
        resultado = service.cadastrar_empresa(
            cnpj="12345678000199",
            razao_social="Empresa Teste",
            nome_fantasia=None,
            certificado_path="/path/to/cert.pfx",
            certificado_senha="errada"
        )
        
        assert resultado['success'] is False
        assert 'inválido' in resultado['error']
        service.repository.create.assert_not_called()
    
    def test_rejeita_certificado_expirado(self, service):
        """Deve rejeitar empresa com certificado expirado"""
        service.cert_manager.validate_certificate.return_value = {
            'valid': True,
            'is_expired': True,
            'expiry_date': datetime(2025, 1, 1)
        }
        
        resultado = service.cadastrar_empresa(
            cnpj="12345678000199",
            razao_social="Empresa Teste",
            nome_fantasia=None,
            certificado_path="/path/to/cert.pfx",
            certificado_senha="senha123"
        )
        
        assert resultado['success'] is False
        assert 'expirado' in resultado['error'].lower()
        service.repository.create.assert_not_called()
    
    def test_rejeita_cnpj_duplicado(self, service, cert_info_valido):
        """Deve rejeitar empresa com CNPJ já cadastrado"""
        service.cert_manager.validate_certificate.return_value = cert_info_valido
        service.repository.get_by_cnpj.return_value = Empresa(
            id=1, cnpj="12345678000199", razao_social="Existente"
        )
        
        resultado = service.cadastrar_empresa(
            cnpj="12345678000199",
            razao_social="Empresa Nova",
            nome_fantasia=None,
            certificado_path="/path/to/cert.pfx",
            certificado_senha="senha123"
        )
        
        assert resultado['success'] is False
        assert 'já cadastrada' in resultado['error'].lower()
        service.repository.create.assert_not_called()


class TestExcluirEmpresa:
    """Testes para excluir_empresa"""
    
    def test_exclui_empresa_e_certificado(self, service, tmp_path):
        """Deve excluir empresa e remover arquivo do certificado"""
        cert_file = tmp_path / "cert.pfx"
        cert_file.write_text("fake cert data")
        
        service.repository.get_by_id.return_value = Empresa(
            id=1,
            cnpj="12345678000199",
            razao_social="Teste",
            certificado_path=str(cert_file)
        )
        service.repository.delete.return_value = True
        
        resultado = service.excluir_empresa(1)
        
        assert resultado is True
        assert not cert_file.exists()  # Arquivo deve ter sido removido
        service.repository.delete.assert_called_once_with(1)


class TestValidarCertificado:
    """Testes para validar_certificado_empresa"""
    
    def test_valida_certificado_existente(self, service, cert_info_valido):
        """Deve validar certificado de empresa existente"""
        service.repository.get_by_id.return_value = Empresa(
            id=1,
            cnpj="12345678000199",
            razao_social="Teste",
            certificado_path="/path/to/cert.pfx",
            certificado_senha="senha123"
        )
        service.cert_manager.validate_certificate.return_value = cert_info_valido
        
        resultado = service.validar_certificado_empresa(1)
        
        assert resultado['valid'] is True
    
    def test_empresa_nao_encontrada(self, service):
        """Deve retornar erro se empresa não existe"""
        service.repository.get_by_id.return_value = None
        
        resultado = service.validar_certificado_empresa(999)
        
        assert resultado['valid'] is False
        assert 'não encontrada' in resultado['error'].lower()
