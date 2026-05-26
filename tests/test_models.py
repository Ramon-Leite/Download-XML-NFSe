"""
Testes unitários para os modelos Empresa e NFSe
"""
import pytest
from datetime import date, datetime
from decimal import Decimal

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.models import Empresa, NFSe


class TestEmpresa:
    """Testes para o modelo Empresa"""
    
    def test_cnpj_limpeza_formatado(self):
        """CNPJ com formatação deve ser limpo"""
        empresa = Empresa(cnpj="12.345.678/0001-99", razao_social="Teste")
        assert empresa.cnpj == "12345678000199"
    
    def test_cnpj_sem_formatacao(self):
        """CNPJ já limpo deve permanecer igual"""
        empresa = Empresa(cnpj="12345678000199", razao_social="Teste")
        assert empresa.cnpj == "12345678000199"
    
    def test_cnpj_formatado_property(self):
        """Property cnpj_formatado deve retornar formato XX.XXX.XXX/XXXX-XX"""
        empresa = Empresa(cnpj="12345678000199", razao_social="Teste")
        assert empresa.cnpj_formatado == "12.345.678/0001-99"
    
    def test_cnpj_formatado_invalido(self):
        """CNPJ com tamanho inválido retorna sem formatação"""
        empresa = Empresa(cnpj="123", razao_social="Teste")
        assert empresa.cnpj_formatado == "123"
    
    def test_to_dict(self):
        """to_dict deve retornar dicionário com todas as chaves"""
        empresa = Empresa(cnpj="12345678000199", razao_social="Teste LTDA")
        d = empresa.to_dict()
        
        assert d['cnpj'] == "12345678000199"
        assert d['razao_social'] == "Teste LTDA"
        assert 'id' in d
        assert 'certificado_path' in d
        assert 'ativo' in d
    
    def test_defaults(self):
        """Valores padrão devem ser corretos"""
        empresa = Empresa()
        assert empresa.ativo is True
        assert empresa.ultimo_nsu == 0
        assert empresa.id is None


class TestNFSe:
    """Testes para o modelo NFSe"""
    
    def test_cnpj_prestador_limpeza(self):
        """CNPJ do prestador com formatação deve ser limpo"""
        nfse = NFSe(prestador_cnpj="12.345.678/0001-99")
        assert nfse.prestador_cnpj == "12345678000199"
    
    def test_cnpj_tomador_limpeza(self):
        """CNPJ do tomador com formatação deve ser limpo"""
        nfse = NFSe(tomador_cnpj="98.765.432/0001-88")
        assert nfse.tomador_cnpj == "98765432000188"
    
    def test_formatar_cnpj_valido(self):
        """formatar_cnpj deve funcionar com CNPJ de 14 dígitos"""
        assert NFSe.formatar_cnpj("12345678000199") == "12.345.678/0001-99"
    
    def test_formatar_cnpj_invalido(self):
        """formatar_cnpj com tamanho errado retorna original"""
        assert NFSe.formatar_cnpj("123") == "123"
    
    def test_formatar_cnpj_none(self):
        """formatar_cnpj com None retorna string vazia"""
        assert NFSe.formatar_cnpj(None) == ""
    
    def test_formatar_cnpj_vazio(self):
        """formatar_cnpj com string vazia retorna string vazia"""
        assert NFSe.formatar_cnpj("") == ""
    
    def test_prestador_cnpj_formatado(self):
        """Property prestador_cnpj_formatado deve funcionar"""
        nfse = NFSe(prestador_cnpj="12345678000199")
        assert nfse.prestador_cnpj_formatado == "12.345.678/0001-99"
    
    def test_tomador_cnpj_formatado(self):
        """Property tomador_cnpj_formatado deve funcionar"""
        nfse = NFSe(tomador_cnpj="98765432000188")
        assert nfse.tomador_cnpj_formatado == "98.765.432/0001-88"
    
    def test_to_dict_com_valores(self):
        """to_dict deve converter valores corretamente"""
        nfse = NFSe(
            empresa_id=1,
            chave_acesso="ABC123",
            tipo="EMITIDA",
            data_emissao=date(2025, 12, 23),
            valor_servicos=Decimal("1500.00")
        )
        d = nfse.to_dict()
        
        assert d['data_emissao'] == "2025-12-23"
        assert d['valor_servicos'] == 1500.00
        assert d['tipo'] == "EMITIDA"
    
    def test_to_dict_com_none(self):
        """to_dict deve lidar com valores None"""
        nfse = NFSe()
        d = nfse.to_dict()
        
        assert d['data_emissao'] is None
        assert d['valor_servicos'] is None
    
    def test_defaults(self):
        """Valores padrão devem ser corretos"""
        nfse = NFSe()
        assert nfse.tipo == "EMITIDA"
        assert nfse.status == "NORMAL"
        assert nfse.id is None
