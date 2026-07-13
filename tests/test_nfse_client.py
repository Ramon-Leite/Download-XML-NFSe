"""
Testes unitários para NFSeClient (paginação por NSU e rate limit)
"""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.nfse_client import NFSeClient


@pytest.fixture
def client():
    """Cliente com sessão HTTP mockada (não faz requisições reais)"""
    with patch.object(NFSeClient, '_create_session', return_value=MagicMock()):
        yield NFSeClient('/tmp/cert.pem', '/tmp/key.pem')


def _lote(nsus):
    """Resposta da API com documentos nos NSUs informados"""
    return {
        'StatusProcessamento': 'DOCUMENTOS_LOCALIZADOS',
        'LoteDFe': [{'NSU': n, 'TipoDocumento': 'NFSE', 'ArquivoXml': 'x'} for n in nsus]
    }


VAZIO = {'StatusProcessamento': 'NENHUM_DOCUMENTO_LOCALIZADO', 'LoteDFe': []}


class TestIterarLotesDfe:
    """Testes para a paginação por NSU"""

    def test_continua_apos_lote_parcial(self, client):
        """
        REGRESSÃO (bug das notas sumidas): um lote com menos de 50
        documentos NÃO significa fim da fila — a iteração deve continuar
        até a API responder sem documentos.
        """
        respostas = [
            _lote(range(1, 31)),    # lote parcial: 30 docs
            _lote(range(31, 46)),   # ainda há mais 15 docs!
            VAZIO,
        ]
        with patch.object(client, 'buscar_por_nsu', side_effect=respostas) as mock_busca:
            lotes = list(client.iterar_lotes_dfe(0))

        total_docs = sum(len(l) for l in lotes)
        assert total_docs == 45  # os 15 do segundo lote não podem ser perdidos
        # Pediu o próximo NSU após o maior de cada lote
        assert mock_busca.call_args_list[1][0][0] == 31
        assert mock_busca.call_args_list[2][0][0] == 46

    def test_para_quando_nao_ha_documentos(self, client):
        """Resposta sem documentos encerra a iteração"""
        with patch.object(client, 'buscar_por_nsu', side_effect=[VAZIO]):
            lotes = list(client.iterar_lotes_dfe(0))
        assert lotes == []

    def test_para_quando_resposta_none(self, client):
        """404/None encerra a iteração sem erro"""
        with patch.object(client, 'buscar_por_nsu', side_effect=[None]):
            lotes = list(client.iterar_lotes_dfe(100))
        assert lotes == []

    def test_lotes_ordenados_por_nsu(self, client):
        """Documentos de cada lote devem vir ordenados por NSU"""
        respostas = [_lote([5, 3, 4]), VAZIO]
        with patch.object(client, 'buscar_por_nsu', side_effect=respostas):
            lotes = list(client.iterar_lotes_dfe(0))

        assert [d['NSU'] for d in lotes[0]] == [3, 4, 5]

    def test_avanca_mesmo_com_nsu_repetido(self, client):
        """Proteção contra loop infinito se a API repetir NSUs"""
        respostas = [_lote([10]), _lote([10]), VAZIO]
        with patch.object(client, 'buscar_por_nsu', side_effect=respostas) as mock_busca:
            list(client.iterar_lotes_dfe(10))

        # Segunda chamada precisa pedir NSU > 10
        assert mock_busca.call_args_list[1][0][0] == 11


class TestRateLimit:
    """Testes para o tratamento de 429"""

    def test_429_espera_e_tenta_novamente(self, client):
        """429 deve esperar (backoff) e repetir, sem consumir tentativas de erro"""
        resp_429 = MagicMock(status_code=429)
        resp_ok = MagicMock(status_code=200)
        client.session.request.side_effect = [resp_429, resp_429, resp_ok]

        with patch('api.nfse_client.time.sleep') as mock_sleep:
            response = client._make_request('GET', '/contribuintes/DFe/0')

        assert response.status_code == 200
        assert mock_sleep.call_count == 2
        # Backoff exponencial: segunda espera maior que a primeira
        assert mock_sleep.call_args_list[1][0][0] > mock_sleep.call_args_list[0][0][0]

    def test_429_persistente_estoura_excecao(self, client):
        """429 sem fim deve estourar exceção clara (não loop infinito)"""
        client.session.request.return_value = MagicMock(status_code=429)

        with patch('api.nfse_client.time.sleep'):
            with pytest.raises(Exception, match="Rate limit"):
                client._make_request('GET', '/contribuintes/DFe/0')
