"""
Testes da busca ativa de notas faltantes (recuperação via DPS na SEFIN Nacional)
"""
import base64
import gzip
import pytest
import sqlite3
from datetime import date
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.models import Empresa, NFSe
from database.repository import EmpresaRepository, NFSeRepository
from database.schema import init_database
from services.download_service import DownloadService
from api.nfse_client import NFSeClient


# ---------------------------------------------------------------------------
# Montagem do id da DPS
# ---------------------------------------------------------------------------

class TestMontarIdDps:
    def test_formato_padrao(self):
        id_dps = DownloadService.montar_id_dps(
            cmun='3304557',            # Rio de Janeiro
            cnpj='12345678000199',
            serie='900',
            numero_dps=42
        )
        # DPS + cMun(7) + tpInsc(1) + inscrição(14) + série(5) + nDPS(15) = 45 chars
        esperado = 'DPS' + '3304557' + '2' + '12345678000199' + '00900' + '42'.zfill(15)
        assert id_dps == esperado
        assert len(id_dps) == 45
        assert id_dps.startswith('DPS')
        assert id_dps[3:].isdigit()

    def test_serie_com_zeros_e_texto(self):
        id_dps = DownloadService.montar_id_dps('3304557', '12345678000199', '00001', 7)
        assert id_dps[25:30] == '00001'  # série zero-padded em 5

        id_dps2 = DownloadService.montar_id_dps('3304557', '12345678000199', 'A1', 7)
        assert id_dps2[25:30] == '00001'  # só dígitos da série


# ---------------------------------------------------------------------------
# Detecção de lacunas de DPS no repositório
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_db(tmp_path):
    db_path = tmp_path / "test_nfse.db"
    with patch('config.DATABASE_PATH', db_path):
        init_database()
        yield db_path


@pytest.fixture
def repos(temp_db):
    emp_repo = EmpresaRepository()
    emp_repo.db_path = temp_db
    nfse_repo = NFSeRepository()
    nfse_repo.db_path = temp_db
    return emp_repo, nfse_repo


def _chave(cmun='3304557', sufixo='1'):
    """Chave de acesso fictícia com 50 dígitos começando pelo cMun"""
    resto = (sufixo * 43)[:43]
    return cmun + resto


def _nota(empresa_id, ndps, chave, serie='900', numero=None):
    return NFSe(
        empresa_id=empresa_id, chave_acesso=chave, numero=numero or str(ndps),
        numero_dps=str(ndps), serie=serie, tipo='EMITIDA',
        data_emissao=date(2026, 6, 1)
    )


class TestDetectarGapsDps:
    def test_detecta_lacunas_por_serie(self, repos):
        emp_repo, nfse_repo = repos
        emp_id = emp_repo.create(Empresa(
            cnpj='12345678000199', razao_social='X',
            certificado_path='/c.pfx', certificado_senha='s'
        ))

        # DPS 1, 2, 5 → faltam 3 e 4
        for ndps, suf in [(1, 'a'), (2, 'b'), (5, 'c')]:
            nfse_repo.create(_nota(emp_id, ndps, _chave(sufixo=str(ndps))))

        gaps = nfse_repo.detectar_gaps_dps(emp_id)
        assert len(gaps) == 1
        assert gaps[0]['serie'] == '900'
        assert gaps[0]['cmun'] == '3304557'
        assert gaps[0]['faltantes'] == [3, 4]

    def test_nota_cancelada_ocupa_numero(self, repos):
        emp_repo, nfse_repo = repos
        emp_id = emp_repo.create(Empresa(
            cnpj='12345678000199', razao_social='X',
            certificado_path='/c.pfx', certificado_senha='s'
        ))

        n1 = _nota(emp_id, 1, _chave(sufixo='1'))
        n2 = _nota(emp_id, 2, _chave(sufixo='2'))
        n2.status = 'CANCELADA'
        n3 = _nota(emp_id, 3, _chave(sufixo='3'))
        for n in (n1, n2, n3):
            nfse_repo.create(n)

        # 1,2,3 completos (a cancelada conta) → sem lacunas
        assert nfse_repo.detectar_gaps_dps(emp_id) == []

    def test_sem_lacunas(self, repos):
        emp_repo, nfse_repo = repos
        emp_id = emp_repo.create(Empresa(
            cnpj='12345678000199', razao_social='X',
            certificado_path='/c.pfx', certificado_senha='s'
        ))
        nfse_repo.create(_nota(emp_id, 1, _chave(sufixo='1')))
        nfse_repo.create(_nota(emp_id, 2, _chave(sufixo='2')))

        assert nfse_repo.detectar_gaps_dps(emp_id) == []


# ---------------------------------------------------------------------------
# Consultas SEFIN no cliente
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    with patch.object(NFSeClient, '_create_session', return_value=MagicMock()):
        yield NFSeClient('/tmp/cert.pem', '/tmp/key.pem')


def _xml_gzip_b64(xml: str) -> str:
    return base64.b64encode(gzip.compress(xml.encode('utf-8'))).decode('ascii')


class TestConsultasSefin:
    def test_consultar_chave_por_dps_ok(self, client):
        resp = MagicMock(status_code=200)
        resp.json.return_value = {'chaveAcesso': '3304557' + '0' * 43}
        with patch.object(client, '_make_request', return_value=resp) as mock_req:
            chave = client.consultar_chave_por_dps('DPS' + '1' * 42)

        assert chave == '3304557' + '0' * 43
        # Deve consultar a SEFIN, não o ADN
        assert mock_req.call_args.kwargs.get('base_url') is not None

    def test_consultar_chave_por_dps_404(self, client):
        resp = MagicMock(status_code=404)
        with patch.object(client, '_make_request', return_value=resp):
            assert client.consultar_chave_por_dps('DPS' + '1' * 42) is None

    def test_consultar_chave_por_dps_403_estoura_erro(self, client):
        """403 (ex.: certificado vencido) é erro sistêmico, não lacuna legítima"""
        resp = MagicMock(status_code=403)
        with patch.object(client, '_make_request', return_value=resp):
            with pytest.raises(RuntimeError, match="403"):
                client.consultar_chave_por_dps('DPS' + '1' * 42)

    def test_consultar_nfse_por_chave_decodifica_gzip(self, client):
        xml = '<NFSe><infNFSe><nNFSe>77</nNFSe></infNFSe></NFSe>'
        resp = MagicMock(status_code=200)
        resp.json.return_value = {'nfseXmlGZipB64': _xml_gzip_b64(xml)}
        with patch.object(client, '_make_request', return_value=resp):
            resultado = client.consultar_nfse_por_chave('3304557' + '0' * 43)

        assert resultado == xml

    def test_decodificar_fallback_base64_puro(self, client):
        xml = '<NFSe>abc</NFSe>'
        puro = base64.b64encode(xml.encode()).decode()
        assert client._decodificar_xml_gzip_b64(puro) == xml

    def test_decodificar_fallback_xml_cru(self, client):
        xml = '<NFSe>abc</NFSe>'
        assert client._decodificar_xml_gzip_b64(xml) == xml


# ---------------------------------------------------------------------------
# Serviço de recuperação
# ---------------------------------------------------------------------------

@pytest.fixture
def empresa():
    return Empresa(
        id=1, cnpj='12345678000199', razao_social='Empresa Teste LTDA',
        certificado_path='/path/to/cert.pfx', certificado_senha='senha123',
        ultimo_nsu=100, ativo=True
    )


@pytest.fixture
def service(tmp_path):
    with patch('services.download_service.NFSeRepository'), \
         patch('services.download_service.EmpresaRepository'), \
         patch('services.download_service.EventoPendenteRepository'), \
         patch('services.download_service.SchedulerConfigRepository') as mock_sched, \
         patch('services.download_service.CertificateManager'), \
         patch('services.download_service.XMLParser'), \
         patch('services.download_service.config.XMLS_DIR', tmp_path), \
         patch('services.download_service.time.sleep'):

        mock_sched.return_value.get.return_value = None
        svc = DownloadService()
        svc.evento_pendente_repository.get_by_chave.return_value = []
        yield svc


class TestBuscarNotasFaltantes:
    def _mock_client(self):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        return mock_client

    def test_recupera_nota_existente_na_sefin(self, service, empresa):
        service.cert_manager.convert_pfx_to_pem.return_value = ('/tmp/c.pem', '/tmp/k.pem')
        service.nfse_repository.detectar_gaps_dps.return_value = [
            {'serie': '900', 'cmun': '3304557', 'faltantes': [3], 'primeiro': 1, 'ultimo': 5}
        ]
        service.nfse_repository.exists_by_chave.return_value = False

        mock_client = self._mock_client()
        mock_client.consultar_chave_por_dps.return_value = '3304557' + '9' * 43
        mock_client.consultar_nfse_por_chave.return_value = '<xml>nota</xml>'

        service.xml_parser.parse_nfse.return_value = {
            'chave_acesso': '3304557' + '9' * 43,
            'numero': '3',
            'data_emissao': date(2026, 6, 3),
            'prestador_cnpj': '12345678000199',
            'tomador_cnpj': '99999999000199',
            'status': 'NORMAL',
            'is_evento': False
        }

        with patch('services.download_service.NFSeClient', return_value=mock_client):
            stats = service.buscar_notas_faltantes(empresa)

        assert stats['faltantes_detectadas'] == 1
        assert stats['consultadas'] == 1
        assert stats['recuperadas'] == 1
        assert stats['erros'] == 0
        service.nfse_repository.create.assert_called_once()

        # Verificar o id da DPS montado
        id_usado = mock_client.consultar_chave_por_dps.call_args[0][0]
        assert id_usado == DownloadService.montar_id_dps('3304557', '12345678000199', '900', 3)

    def test_lacuna_legitima_dps_sem_nfse(self, service, empresa):
        service.cert_manager.convert_pfx_to_pem.return_value = ('/tmp/c.pem', '/tmp/k.pem')
        service.nfse_repository.detectar_gaps_dps.return_value = [
            {'serie': '900', 'cmun': '3304557', 'faltantes': [3, 4], 'primeiro': 1, 'ultimo': 5}
        ]

        mock_client = self._mock_client()
        mock_client.consultar_chave_por_dps.return_value = None  # DPS nunca virou NFSe

        with patch('services.download_service.NFSeClient', return_value=mock_client):
            stats = service.buscar_notas_faltantes(empresa)

        assert stats['consultadas'] == 2
        assert stats['sem_nfse'] == 2
        assert stats['recuperadas'] == 0
        assert stats['erros'] == 0
        service.nfse_repository.create.assert_not_called()

    def test_sem_lacunas_nao_consulta(self, service, empresa):
        service.nfse_repository.detectar_gaps_dps.return_value = []

        stats = service.buscar_notas_faltantes(empresa)

        assert stats['faltantes_detectadas'] == 0
        assert stats['consultadas'] == 0
        # Nem converteu certificado
        service.cert_manager.convert_pfx_to_pem.assert_not_called()

    def test_respeita_limite_de_consultas(self, service, empresa):
        service.cert_manager.convert_pfx_to_pem.return_value = ('/tmp/c.pem', '/tmp/k.pem')
        service.nfse_repository.detectar_gaps_dps.return_value = [
            {'serie': '900', 'cmun': '3304557', 'faltantes': list(range(1, 100)), 'primeiro': 1, 'ultimo': 100}
        ]

        mock_client = self._mock_client()
        mock_client.consultar_chave_por_dps.return_value = None

        with patch('services.download_service.NFSeClient', return_value=mock_client):
            stats = service.buscar_notas_faltantes(empresa, max_consultas=10)

        assert stats['consultadas'] == 10

    def test_serie_com_salto_de_numeracao_e_ignorada(self, service, empresa):
        service.cert_manager.convert_pfx_to_pem.return_value = ('/tmp/c.pem', '/tmp/k.pem')
        service.nfse_repository.detectar_gaps_dps.return_value = [
            {'serie': '900', 'cmun': '3304557', 'faltantes': list(range(2, 1500)), 'primeiro': 1, 'ultimo': 1500}
        ]

        mock_client = self._mock_client()

        with patch('services.download_service.NFSeClient', return_value=mock_client):
            stats = service.buscar_notas_faltantes(empresa)

        assert stats['consultadas'] == 0
        mock_client.consultar_chave_por_dps.assert_not_called()
        assert any('salto' in d for d in stats['detalhes'])

    def test_erro_sistemico_aborta_execucao(self, service, empresa):
        """Certificado vencido (403) deve abortar a execução com erro claro"""
        service.cert_manager.convert_pfx_to_pem.return_value = ('/tmp/c.pem', '/tmp/k.pem')
        service.nfse_repository.detectar_gaps_dps.return_value = [
            {'serie': '900', 'cmun': '3304557', 'faltantes': [3, 4, 5], 'primeiro': 1, 'ultimo': 6}
        ]

        mock_client = self._mock_client()
        mock_client.consultar_chave_por_dps.side_effect = RuntimeError(
            "Consulta DPS retornou 403 — verifique o certificado da empresa"
        )

        with patch('services.download_service.NFSeClient', return_value=mock_client):
            stats = service.buscar_notas_faltantes(empresa)

        # Abortou na primeira consulta (não insistiu nas demais)
        assert mock_client.consultar_chave_por_dps.call_count == 1
        assert stats['erros'] == 1
        assert stats['sem_nfse'] == 0
        assert any('403' in d for d in stats['detalhes'])

    def test_prestador_divergente_vai_para_quarentena(self, service, empresa, tmp_path):
        service.cert_manager.convert_pfx_to_pem.return_value = ('/tmp/c.pem', '/tmp/k.pem')
        service.nfse_repository.detectar_gaps_dps.return_value = [
            {'serie': '900', 'cmun': '3304557', 'faltantes': [3], 'primeiro': 1, 'ultimo': 5}
        ]
        service.nfse_repository.exists_by_chave.return_value = False

        mock_client = self._mock_client()
        mock_client.consultar_chave_por_dps.return_value = '3304557' + '9' * 43
        mock_client.consultar_nfse_por_chave.return_value = '<xml>nota</xml>'

        service.xml_parser.parse_nfse.return_value = {
            'chave_acesso': '3304557' + '9' * 43,
            'prestador_cnpj': '00000000000000',  # OUTRO CNPJ
            'is_evento': False
        }

        with patch('services.download_service.NFSeClient', return_value=mock_client):
            stats = service.buscar_notas_faltantes(empresa)

        assert stats['erros'] == 1
        assert stats['recuperadas'] == 0
        service.nfse_repository.create.assert_not_called()
        quarentena = list((tmp_path / empresa.cnpj / 'quarentena').glob('*'))
        assert len(quarentena) == 1
