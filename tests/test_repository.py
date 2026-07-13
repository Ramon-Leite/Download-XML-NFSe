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

    def test_mesma_chave_para_duas_empresas(self, empresa_repo, nfse_repo, sample_empresa):
        """
        REGRESSÃO: a mesma nota deve poder existir para duas empresas
        cadastradas (uma como prestadora, outra como tomadora).
        """
        empresa_a_id = empresa_repo.create(sample_empresa)
        empresa_b = Empresa(
            cnpj="99999999000199",
            razao_social="Empresa Tomadora LTDA",
            certificado_path="/path/to/cert2.pfx",
            certificado_senha="senha456",
            ativo=True
        )
        empresa_b_id = empresa_repo.create(empresa_b)

        chave = "CHAVE_COMPARTILHADA"
        nfse_repo.create(NFSe(
            empresa_id=empresa_a_id, chave_acesso=chave,
            tipo="EMITIDA", data_emissao=date(2026, 6, 30)
        ))
        # A mesma chave para a OUTRA empresa não pode falhar
        nfse_repo.create(NFSe(
            empresa_id=empresa_b_id, chave_acesso=chave,
            tipo="RECEBIDA", data_emissao=date(2026, 6, 30)
        ))

        # Dedupe é por empresa
        assert nfse_repo.exists_by_chave(chave, empresa_id=empresa_a_id) is True
        assert nfse_repo.exists_by_chave(chave, empresa_id=empresa_b_id) is True
        assert nfse_repo.exists_by_chave(chave, empresa_id=999) is False

        # E o evento enxerga as duas cópias
        assert len(nfse_repo.get_all_by_chave(chave)) == 2

    def test_duplicata_mesma_empresa_falha(self, empresa_repo, nfse_repo, sample_empresa):
        """A MESMA empresa não pode ter a mesma chave duas vezes"""
        empresa_id = empresa_repo.create(sample_empresa)
        nfse_repo.create(NFSe(
            empresa_id=empresa_id, chave_acesso="CHAVE_UNICA",
            tipo="EMITIDA", data_emissao=date(2026, 6, 30)
        ))
        with pytest.raises(sqlite3.IntegrityError):
            nfse_repo.create(NFSe(
                empresa_id=empresa_id, chave_acesso="CHAVE_UNICA",
                tipo="EMITIDA", data_emissao=date(2026, 6, 30)
            ))

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

    def test_gaps_ignora_notas_substituidas_e_canceladas(self, empresa_repo, nfse_repo, sample_empresa):
        """
        REGRESSÃO: uma nota substituída/cancelada existe e ocupa o número —
        não pode aparecer como 'faltante'. Só números realmente ausentes contam.
        """
        empresa_id = empresa_repo.create(sample_empresa)

        # Números 1..5: #2 substituída, #4 cancelada, #3 realmente ausente
        definicoes = [
            (1, 'NORMAL'),
            (2, 'SUBSTITUIDA'),
            (4, 'CANCELADA'),
            (5, 'NORMAL'),
        ]
        for numero, status in definicoes:
            nota = NFSe(
                empresa_id=empresa_id, chave_acesso=f"CHAVE_GAP_{numero}",
                numero=str(numero), tipo="EMITIDA", data_emissao=date(2026, 6, 1),
                status=status
            )
            nfse_repo.create(nota)

        gaps = nfse_repo.detectar_gaps_numeracao(empresa_id)

        # Apenas #3 falta de verdade; #2 e #4 existem (substituída/cancelada)
        assert gaps['numeros_faltantes'] == [3]
        assert gaps['primeiro'] == 1
        assert gaps['ultimo'] == 5
        assert gaps['total'] == 4


class TestMigracaoDedupePorEmpresa:
    """Testes da migração de UNIQUE(chave_acesso) para UNIQUE(empresa_id, chave_acesso)"""

    def test_migra_banco_antigo_preservando_dados(self, tmp_path):
        db_path = tmp_path / "old_nfse.db"

        # Criar banco no formato ANTIGO (chave única global)
        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE empresas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cnpj TEXT UNIQUE NOT NULL,
                razao_social TEXT NOT NULL,
                nome_fantasia TEXT,
                certificado_path TEXT NOT NULL,
                certificado_senha TEXT NOT NULL,
                ultimo_nsu INTEGER DEFAULT 0,
                ativo BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE nfse (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL,
                chave_acesso TEXT UNIQUE NOT NULL,
                numero TEXT,
                serie TEXT,
                tipo TEXT NOT NULL CHECK(tipo IN ('EMITIDA', 'RECEBIDA')),
                data_emissao DATE NOT NULL,
                data_competencia DATE,
                prestador_cnpj TEXT,
                prestador_nome TEXT,
                tomador_cnpj TEXT,
                tomador_nome TEXT,
                valor_servicos DECIMAL(15, 2),
                valor_iss DECIMAL(15, 2),
                codigo_servico TEXT,
                descricao_servico TEXT,
                status TEXT DEFAULT 'NORMAL' CHECK(status IN ('NORMAL', 'CANCELADA', 'SUBSTITUIDA')),
                xml_path TEXT,
                downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE
            );
            INSERT INTO empresas (cnpj, razao_social, certificado_path, certificado_senha)
                VALUES ('11111111000111', 'Empresa A', '/c.pfx', 's');
            INSERT INTO empresas (cnpj, razao_social, certificado_path, certificado_senha)
                VALUES ('22222222000122', 'Empresa B', '/c.pfx', 's');
            INSERT INTO nfse (empresa_id, chave_acesso, numero, tipo, data_emissao, valor_servicos)
                VALUES (1, 'CHAVE_MIGRADA', '77', 'EMITIDA', '2026-05-10', 500.0);
        """)
        conn.commit()
        conn.close()

        # Rodar init_database (que dispara a migração)
        with patch('config.DATABASE_PATH', db_path):
            init_database()

        repo = NFSeRepository()
        repo.db_path = db_path

        # Dados antigos preservados
        nota = repo.get_by_chave('CHAVE_MIGRADA')
        assert nota is not None
        assert nota.numero == '77'
        assert nota.empresa_id == 1

        # Agora a mesma chave pode existir para OUTRA empresa
        repo.create(NFSe(
            empresa_id=2, chave_acesso='CHAVE_MIGRADA',
            tipo='RECEBIDA', data_emissao=date(2026, 5, 10)
        ))
        assert len(repo.get_all_by_chave('CHAVE_MIGRADA')) == 2

        # Mas continua bloqueada para a MESMA empresa
        with pytest.raises(sqlite3.IntegrityError):
            repo.create(NFSe(
                empresa_id=1, chave_acesso='CHAVE_MIGRADA',
                tipo='EMITIDA', data_emissao=date(2026, 5, 10)
            ))

    def test_migracao_e_idempotente(self, tmp_path):
        """Rodar init_database duas vezes não pode quebrar nem duplicar"""
        db_path = tmp_path / "new_nfse.db"
        with patch('config.DATABASE_PATH', db_path):
            init_database()
            init_database()

        conn = sqlite3.connect(db_path)
        sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='nfse'"
        ).fetchone()[0]
        conn.close()
        assert 'UNIQUE(empresa_id, chave_acesso)' in sql


class TestValidDateFields:
    """Testes para a constante VALID_DATE_FIELDS"""
    
    def test_contem_campos_esperados(self):
        assert 'data_emissao' in VALID_DATE_FIELDS
        assert 'data_competencia' in VALID_DATE_FIELDS
    
    def test_nao_contem_campos_invalidos(self):
        assert 'id' not in VALID_DATE_FIELDS
        assert 'chave_acesso' not in VALID_DATE_FIELDS
