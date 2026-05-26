"""
Testes unitários para XMLParser
"""
import pytest
from datetime import date
from decimal import Decimal

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.xml_parser import XMLParser


class TestParseDate:
    """Testes para o método _parse_date"""
    
    def test_formato_iso(self):
        assert XMLParser._parse_date("2025-12-23") == date(2025, 12, 23)
    
    def test_formato_brasileiro(self):
        assert XMLParser._parse_date("23/12/2025") == date(2025, 12, 23)
    
    def test_formato_compacto(self):
        assert XMLParser._parse_date("20251223") == date(2025, 12, 23)
    
    def test_formato_datetime_iso(self):
        assert XMLParser._parse_date("2025-12-23T14:30:00") == date(2025, 12, 23)
    
    def test_formato_datetime_espaco(self):
        assert XMLParser._parse_date("2025-12-23 14:30:00") == date(2025, 12, 23)
    
    def test_none_retorna_none(self):
        assert XMLParser._parse_date(None) is None
    
    def test_string_vazia_retorna_none(self):
        assert XMLParser._parse_date("") is None
    
    def test_string_invalida_retorna_none(self):
        assert XMLParser._parse_date("abc") is None


class TestParseDecimal:
    """Testes para o método _parse_decimal"""
    
    def test_valor_com_ponto(self):
        assert XMLParser._parse_decimal("1234.56") == Decimal("1234.56")
    
    def test_valor_com_virgula(self):
        assert XMLParser._parse_decimal("1234,56") == Decimal("1234.56")
    
    def test_valor_inteiro(self):
        assert XMLParser._parse_decimal("1234") == Decimal("1234")
    
    def test_valor_com_espacos(self):
        assert XMLParser._parse_decimal("  1234.56  ") == Decimal("1234.56")
    
    def test_none_retorna_none(self):
        assert XMLParser._parse_decimal(None) is None
    
    def test_string_vazia_retorna_none(self):
        assert XMLParser._parse_decimal("") is None
    
    def test_string_invalida_retorna_none(self):
        assert XMLParser._parse_decimal("abc") is None


class TestValidateXml:
    """Testes para o método validate_xml"""
    
    def test_xml_valido(self):
        xml = "<root><child>text</child></root>"
        assert XMLParser.validate_xml(xml) is True
    
    def test_xml_invalido(self):
        xml = "<root><child>text</root>"
        assert XMLParser.validate_xml(xml) is False
    
    def test_xml_vazio(self):
        assert XMLParser.validate_xml("") is False
    
    def test_xml_nao_xml(self):
        assert XMLParser.validate_xml("not xml at all") is False


class TestParseNfse:
    """Testes para o método parse_nfse"""
    
    SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
    <NFSe>
        <infNFSe Id="NFSe12345678901234567890123456789012345678901234">
            <nNFSe>000001</nNFSe>
            <sSerie>NFSe</sSerie>
            <dtEmi>2025-12-23</dtEmi>
            <dCompet>2025-12-01</dCompet>
            <emit>
                <CNPJ>12345678000199</CNPJ>
                <xNome>Empresa Prestadora LTDA</xNome>
            </emit>
            <toma>
                <CNPJ>98765432000188</CNPJ>
                <xNome>Empresa Tomadora LTDA</xNome>
            </toma>
            <ValorServicos>1500.00</ValorServicos>
            <ValorIss>75.00</ValorIss>
            <ItemListaServico>01.01</ItemListaServico>
            <Discriminacao>Servico de consultoria</Discriminacao>
            <Status>1</Status>
        </infNFSe>
    </NFSe>
    """
    
    def test_parse_basico(self):
        result = XMLParser.parse_nfse(self.SAMPLE_XML)
        assert result is not None
    
    def test_parse_numero(self):
        result = XMLParser.parse_nfse(self.SAMPLE_XML)
        assert result['numero'] == '000001'
    
    def test_parse_data_emissao(self):
        result = XMLParser.parse_nfse(self.SAMPLE_XML)
        assert result['data_emissao'] == date(2025, 12, 23)
    
    def test_parse_data_competencia(self):
        result = XMLParser.parse_nfse(self.SAMPLE_XML)
        assert result['data_competencia'] == date(2025, 12, 1)
    
    def test_parse_prestador(self):
        result = XMLParser.parse_nfse(self.SAMPLE_XML)
        assert result['prestador_cnpj'] == '12345678000199'
        assert result['prestador_nome'] == 'Empresa Prestadora LTDA'
    
    def test_parse_tomador(self):
        result = XMLParser.parse_nfse(self.SAMPLE_XML)
        assert result['tomador_cnpj'] == '98765432000188'
        assert result['tomador_nome'] == 'Empresa Tomadora LTDA'
    
    def test_parse_valores(self):
        result = XMLParser.parse_nfse(self.SAMPLE_XML)
        assert result['valor_servicos'] == Decimal('1500.00')
        assert result['valor_iss'] == Decimal('75.00')
    
    def test_parse_status_normal(self):
        result = XMLParser.parse_nfse(self.SAMPLE_XML)
        assert result['status'] == 'NORMAL'
    
    def test_parse_xml_invalido(self):
        result = XMLParser.parse_nfse("not xml")
        assert result is None
