"""
Testes unitários para os repositórios EmpresaRepository e NFSeRepository
"""
import pytest
import sqlite3
import tempfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.models import Empresa, NFSe
from database.repository import EmpresaRepository, NFSeRepository, VALID_DATE_FIELDS
from database.schema import init_database


@pytest.fixture
def temp_db(tmp_path):
    """Cria banco de dados temporário para testes"""
    db_path = tmp_path / "test_nfse.db"
    
    with patch('config.DATABASE_PATH', db_path):
        init_database()
        yield db_path


@pytest.fixture
def empresa_repo(temp_db):
    """Repositório de empresas com banco temporário"""
    repo = EmpresaRepository()
    repo.db_path = temp_db
    return repo


@pytest.fixture
def nfse_repo(temp_db):
    """Repositório de NFS-e com banco temporário"""
    repo = NFSeRepository()
    repo.db_path = temp_db
    return repo


@pytest.fixture
def sample_empresa():
    """Empresa de exemplo para testes"""
    return Empresa(
        cnpj="12345678000199",
        razao_social="Empresa Teste LTDA",
        nome_fantasia="Teste",
        certificado_path="/path/to/cert.pfx",
        certificado_senha="senha123",
        ativo=True
    )


class TestEmpresaRepository:
    """Testes para EmpresaRepository"""
    
    def test_create_and_get(self, empresa_repo, sample_empresa):
        empresa_id = empresa_repo.create(sample_empresa)
        assert empresa_id > 0
        
        empresa = empresa_repo.get_by_id(empresa_id)
        assert empresa is not None
        assert empresa.cnpj == "12345678000199"
        assert empresa.razao_social == "Empresa Teste LTDA"
    
    def test_get_by_cnpj(self, empresa_repo, sample_empresa):
        empresa_repo.create(sample_empresa)
        
        empresa = empresa_repo.get_by_cnpj("12345678000199")
        assert empresa is not None
        assert empresa.razao_social == "Empresa Teste LTDA"
    
    def test_get_by_cnpj_formatado(self, empresa_repo, sample_empresa):
        empresa_repo.create(sample_empresa)
        
        # Deve funcionar com CNPJ formatado
        empresa = empresa_repo.get_by_cnpj("12.345.678/0001-99")
        assert empresa is not None
    
    def test_get_all(self, empresa_repo, sample_empresa):
        empresa_repo.create(sample_empresa)
        
        empresas = empresa_repo.get_all()
        assert len(empresas) == 1
        assert empresas[0].razao_social == "Empresa Teste LTDA"
    
    def test_update(self, empresa_repo, sample_empresa):
        empresa_id = empresa_repo.create(sample_empresa)
        
        empresa = empresa_repo.get_by_id(empresa_id)
        empresa.razao_social = "Novo Nome LTDA"
        result = empresa_repo.update(empresa)
        
        assert result is True
        
        updated = empresa_repo.get_by_id(empresa_id)
        assert updated.razao_social == "Novo Nome LTDA"
    
    def test_delete(self, empresa_repo, sample_empresa):
        empresa_id = empresa_repo.create(sample_empresa)
        
        result = empresa_repo.delete(empresa_id)
        assert result is True
        
        empresa = empresa_repo.get_by_id(empresa_id)
        assert empresa is None
    
    def test_get_nonexistent(self, empresa_repo):
        empresa = empresa_repo.get_by_id(999)
        assert empresa is None


class TestNFSeRepository:
    """Testes para NFSeRepository"""
    
    def test_create_and_get(self, empresa_repo, nfse_repo, sample_empresa):
        empresa_id = empresa_repo.create(sample_empresa)
        
        nfse = NFSe(
            empresa_id=empresa_id,
            chave_acesso="CHAVE_TESTE_123",
            numero="001",
            tipo="EMITIDA",
            data_emissao=date(2025, 12, 23),
            valor_servicos=Decimal("1500.00")
        )
        
        nfse_id = nfse_repo.create(nfse)
        assert nfse_id > 0
        
        found = nfse_repo.get_by_chave("CHAVE_TESTE_123")
        assert found is not None
        assert found.numero == "001"
    
    def test_exists_by_chave(self, empresa_repo, nfse_repo, sample_empresa):
        empresa_id = empresa_repo.create(sample_empresa)
        
        nfse = NFSe(
            empresa_id=empresa_id,
            chave_acesso="CHAVE_EXISTS_TEST",
            tipo="EMITIDA",
            data_emissao=date(2025, 12, 23)
        )
        nfse_repo.create(nfse)
        
        assert nfse_repo.exists_by_chave("CHAVE_EXISTS_TEST") is True
        assert nfse_repo.exists_by_chave("CHAVE_NAO_EXISTE") is False
    
    def test_campo_data_whitelist_valido(self, nfse_repo):
        """Campos válidos devem funcionar sem erro"""
        result = nfse_repo.get_all(campo_data='data_emissao')
        assert isinstance(result, list)
        
        result = nfse_repo.get_all(campo_data='data_competencia')
        assert isinstance(result, list)
    
    def test_campo_data_whitelist_invalido(self, nfse_repo):
        """Campo inválido deve levantar ValueError"""
        with pytest.raises(ValueError, match="Campo de data inválido"):
            nfse_repo.get_all(campo_data='campo_malicioso; DROP TABLE nfse;--')
    
    def test_campo_data_whitelist_sql_injection(self, nfse_repo):
        """Tentativa de SQL injection deve ser bloqueada"""
        with pytest.raises(ValueError):
            nfse_repo.get_all(campo_data="1=1; DROP TABLE nfse;")
    
    def test_count_all(self, empresa_repo, nfse_repo, sample_empresa):
        empresa_id = empresa_repo.create(sample_empresa)
        
        assert nfse_repo.count_all() == 0
        
        for i in range(3):
            nfse = NFSe(
                empresa_id=empresa_id,
                chave_acesso=f"CHAVE_COUNT_{i}",
                tipo="EMITIDA",
                data_emissao=date(2025, 12, 23)
            )
            nfse_repo.create(nfse)
        
        assert nfse_repo.count_all() == 3
        assert nfse_repo.count_all(empresa_id=empresa_id) == 3


class TestValidDateFields:
    """Testes para a constante VALID_DATE_FIELDS"""
    
    def test_contem_campos_esperados(self):
        assert 'data_emissao' in VALID_DATE_FIELDS
        assert 'data_competencia' in VALID_DATE_FIELDS
    
    def test_nao_contem_campos_invalidos(self):
        assert 'id' not in VALID_DATE_FIELDS
        assert 'chave_acesso' not in VALID_DATE_FIELDS
