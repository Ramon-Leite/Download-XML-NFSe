"""
Cliente HTTP para API da NFS-e Nacional com autenticação mTLS
Baseado na documentação oficial (swagger.json)

A API usa distribuição por NSU (Número Sequencial Único):
GET /contribuintes/DFe/{nsu} retorna um lote de até 50 documentos
com NSU IGUAL OU MAIOR ao informado. A paginação correta é pedir
sempre (maior NSU recebido + 1) até a API responder sem documentos.
Um lote com menos de 50 documentos NÃO significa fim da fila.
"""
import requests
import random
import time
import logging
import base64
import gzip
from typing import Optional, List, Dict, Any, Iterator
from datetime import date
import config

logger = logging.getLogger(__name__)


class NFSeClient:
    """Cliente para comunicação com a API da NFS-e Nacional usando distribuição por NSU"""
    
    def __init__(self, cert_path: str, key_path: str):
        """
        Inicializa cliente com certificado para mTLS
        
        Args:
            cert_path: Caminho do certificado .pem
            key_path: Caminho da chave privada .pem
        """
        self.base_url = config.API_BASE_URL
        self.cert_path = cert_path
        self.key_path = key_path
        self.session = self._create_session()
    
    def _create_session(self) -> requests.Session:
        """Cria sessão HTTP com configuração mTLS"""
        session = requests.Session()
        session.cert = (self.cert_path, self.key_path)
        session.verify = True
        session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
        return session
    
    def _make_request(self, method: str, endpoint: str, base_url: Optional[str] = None, **kwargs) -> requests.Response:
        """
        Faz requisição HTTP com retry automático.

        429 (rate limit) tem orçamento próprio de esperas com backoff
        exponencial + jitter — não consome as tentativas de erro real.

        Args:
            base_url: URL base alternativa (ex.: SEFIN Nacional). Padrão: ADN.
        """
        url = f"{base_url or self.base_url}{endpoint}"

        tentativas = 0
        esperas_429 = 0

        while True:
            try:
                logger.info(f"Requisição {method} para {endpoint} (tentativa {tentativas + 1})")

                response = self.session.request(
                    method=method,
                    url=url,
                    timeout=config.REQUEST_TIMEOUT,
                    **kwargs
                )

                logger.info(f"Status: {response.status_code}")

                if response.status_code == 429:
                    esperas_429 += 1
                    if esperas_429 > config.MAX_RATE_LIMIT_WAITS:
                        raise Exception(
                            f"Rate limit persistente (429) após {esperas_429 - 1} esperas"
                        )
                    espera = min(60, config.RETRY_DELAY * (2 ** esperas_429)) + random.uniform(0, 1)
                    logger.warning(f"Rate limit atingido (429). Aguardando {espera:.1f}s...")
                    time.sleep(espera)
                    continue

                if response.status_code < 500:
                    return response

                logger.warning(f"Erro de servidor: {response.status_code}. Tentando novamente...")

            except requests.exceptions.RequestException as e:
                logger.error(f"Erro na requisição: {str(e)}")

                if tentativas >= config.MAX_RETRIES - 1:
                    raise

            tentativas += 1
            if tentativas >= config.MAX_RETRIES:
                raise Exception(f"Falha após {config.MAX_RETRIES} tentativas")

            time.sleep(config.RETRY_DELAY * tentativas + random.uniform(0, 1))
    
    def buscar_por_nsu(self, nsu: int, cnpj_consulta: Optional[str] = None, lote: bool = True) -> Optional[Dict[str, Any]]:
        """
        Busca documentos fiscais por NSU
        
        Args:
            nsu: Número Sequencial Único
            cnpj_consulta: CNPJ para filtrar (opcional)
            lote: Se True, retorna lote de documentos
        
        Returns:
            Resposta da API com documentos ou None se erro
        """
        try:
            params = {'lote': lote}
            if cnpj_consulta:
                params['cnpjConsulta'] = cnpj_consulta
            
            response = self._make_request('GET', f'/contribuintes/DFe/{nsu}', params=params)
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                logger.info(f"NSU {nsu} não encontrado")
                return None
            else:
                logger.error(f"Erro ao buscar NSU {nsu}: {response.status_code}")
                return None
        
        except Exception as e:
            logger.error(f"Erro ao buscar NSU: {str(e)}")
            return None
    
    def iterar_lotes_dfe(self, nsu_inicial: int, max_lotes: int = 2000) -> Iterator[List[Dict[str, Any]]]:
        """
        Itera sobre TODOS os lotes de documentos a partir de um NSU.

        Como a API retorna documentos com NSU >= informado, não existe
        "descoberta de range": basta começar do NSU desejado (0 para tudo)
        e pedir sempre (maior NSU do lote + 1) até a resposta vir vazia.

        Um lote com menos de 50 documentos NÃO encerra a iteração — a
        confirmação de fim é a própria API responder sem documentos.

        Args:
            nsu_inicial: NSU a partir do qual buscar (0 para tudo)
            max_lotes: Trava de segurança contra loop infinito

        Yields:
            Lotes (listas de documentos) ordenados por NSU crescente
        """
        nsu_atual = max(0, nsu_inicial)

        for _ in range(max_lotes):
            resultado = self.buscar_por_nsu(nsu_atual, cnpj_consulta=None, lote=True)

            if not resultado:
                logger.info(f"Fim da distribuição: sem resposta a partir do NSU {nsu_atual}")
                return

            status = resultado.get('StatusProcessamento')

            if status != 'DOCUMENTOS_LOCALIZADOS':
                logger.info(f"Fim da distribuição a partir do NSU {nsu_atual} (status: {status})")
                return

            lote_dfe = resultado.get('LoteDFe', [])
            if not lote_dfe:
                logger.info(f"Fim da distribuição: lote vazio a partir do NSU {nsu_atual}")
                return

            lote_ordenado = sorted(lote_dfe, key=lambda d: d.get('NSU') or 0)
            yield lote_ordenado

            maior_nsu = max((d.get('NSU') or 0) for d in lote_ordenado)
            # Garantir avanço mesmo se a API devolver NSUs inesperados
            nsu_atual = max(maior_nsu + 1, nsu_atual + 1)

        logger.warning(f"Trava de segurança atingida ({max_lotes} lotes) — iteração encerrada")
    
    @staticmethod
    def _decodificar_xml_gzip_b64(valor: str) -> Optional[str]:
        """Decodifica XML em base64+gzip (com fallbacks para base64 puro e XML cru)"""
        if not valor:
            return None
        valor = valor.strip()
        if valor.startswith('<'):
            return valor  # já é XML
        try:
            binario = base64.b64decode(valor)
        except Exception:
            return None
        try:
            return gzip.decompress(binario).decode('utf-8')
        except Exception:
            try:
                texto = binario.decode('utf-8')
                return texto if texto.lstrip().startswith('<') else None
            except Exception:
                return None

    def extrair_xml_documento(self, documento: Dict[str, Any]) -> Optional[str]:
        """
        Extrai e descompacta o XML de um documento

        Args:
            documento: Documento retornado pela API

        Returns:
            XML descompactado ou None
        """
        try:
            arquivo_xml_base64 = documento.get('ArquivoXml')
            if not arquivo_xml_base64:
                return None

            return self._decodificar_xml_gzip_b64(arquivo_xml_base64)

        except Exception as e:
            logger.error(f"Erro ao extrair XML: {str(e)}")
            return None

    @staticmethod
    def _achar_campo(payload: Dict[str, Any], substring: str) -> Optional[str]:
        """Encontra o primeiro valor string cujo nome de campo contém a substring (case-insensitive)"""
        alvo = substring.lower()
        for chave, valor in payload.items():
            if alvo in chave.lower() and isinstance(valor, str) and valor:
                return valor
        return None

    def consultar_chave_por_dps(self, id_dps: str) -> Optional[str]:
        """
        Consulta na SEFIN Nacional se uma DPS gerou NFS-e.

        O id da DPS é derivável (diferente da chave de acesso, que tem
        código aleatório): DPS + cMun(7) + tpInsc(1) + inscrição(14) +
        série(5) + nDPS(15).

        Returns:
            Chave de acesso da NFS-e gerada, ou None se a DPS não gerou nota (404).

        Raises:
            RuntimeError: status inesperado (ex.: 403 por certificado vencido) —
                falha sistêmica que invalida as demais consultas da execução.
        """
        response = self._make_request('GET', f'/dps/{id_dps}', base_url=config.SEFIN_BASE_URL)

        if response.status_code == 404:
            logger.info(f"DPS {id_dps} não gerou NFS-e (404)")
            return None
        if response.status_code != 200:
            raise RuntimeError(
                f"Consulta DPS retornou {response.status_code} — verifique o certificado da empresa"
            )

        payload = response.json()
        if isinstance(payload, str):
            return payload.strip() or None

        # Resposta observada em produção: {"tipoAmbiente", "versaoAplicativo",
        # "dataHoraProcessamento", "chaveAcesso"}
        chave = self._achar_campo(payload, 'chave')
        if not chave:
            logger.warning(f"Resposta da consulta DPS sem campo de chave. Campos: {list(payload.keys())}")
        return chave

    def consultar_nfse_por_chave(self, chave_acesso: str) -> Optional[str]:
        """
        Baixa da SEFIN Nacional o XML de uma NFS-e pela chave de acesso.

        Returns:
            Conteúdo XML da nota, ou None se não encontrada (404).

        Raises:
            RuntimeError: status inesperado (ex.: 403 por certificado vencido).
        """
        response = self._make_request('GET', f'/nfse/{chave_acesso}', base_url=config.SEFIN_BASE_URL)

        if response.status_code == 404:
            logger.info(f"NFS-e {chave_acesso} não encontrada (404)")
            return None
        if response.status_code != 200:
            raise RuntimeError(
                f"Consulta NFS-e retornou {response.status_code} — verifique o certificado da empresa"
            )

        payload = response.json()
        if isinstance(payload, str):
            return self._decodificar_xml_gzip_b64(payload)

        # Resposta observada em produção: {"tipoAmbiente", "versaoAplicativo",
        # "dataHoraProcessamento", "chaveAcesso", "nfseXmlGZipB64"}
        valor_xml = self._achar_campo(payload, 'xml')
        if not valor_xml:
            logger.warning(f"Resposta da consulta NFS-e sem campo de XML. Campos: {list(payload.keys())}")
            return None

        xml = self._decodificar_xml_gzip_b64(valor_xml)
        if not xml:
            logger.warning(f"Não foi possível decodificar o XML da NFS-e {chave_acesso}")
        return xml
    
    def buscar_eventos_nfse(self, chave_acesso: str) -> Optional[Dict[str, Any]]:
        """
        Busca eventos vinculados a uma NFS-e
        
        Args:
            chave_acesso: Chave de acesso da NFS-e
        
        Returns:
            Resposta com eventos ou None
        """
        try:
            response = self._make_request('GET', f'/contribuintes/NFSe/{chave_acesso}/Eventos')
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                logger.info(f"Nenhum evento encontrado para chave {chave_acesso}")
                return None
            else:
                logger.error(f"Erro ao buscar eventos: {response.status_code}")
                return None
        
        except Exception as e:
            logger.error(f"Erro ao buscar eventos: {str(e)}")
            return None
    
    def close(self):
        """Fecha a sessão HTTP"""
        self.session.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
