"""
Cliente HTTP para API da NFS-e Nacional com autenticação mTLS
Baseado na documentação oficial (swagger.json)
A API usa distribuição por NSU (Número Sequencial Único)
"""
import requests
import time
import logging
import base64
import gzip
from typing import Optional, List, Dict, Any
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
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Faz requisição HTTP com retry automático"""
        url = f"{self.base_url}{endpoint}"
        
        for attempt in range(config.MAX_RETRIES):
            try:
                logger.info(f"Requisição {method} para {endpoint} (tentativa {attempt + 1})")
                
                response = self.session.request(
                    method=method,
                    url=url,
                    timeout=config.REQUEST_TIMEOUT,
                    **kwargs
                )
                
                logger.info(f"Status: {response.status_code}")
                
                if response.status_code == 429:
                    logger.warning(f"Rate limit atingindo (429). Aguardando...")
                    time.sleep(config.RETRY_DELAY * 2)
                    continue
                    
                if response.status_code < 500:
                    return response
                
                logger.warning(f"Erro de servidor: {response.status_code}. Tentando novamente...")
                
            except requests.exceptions.RequestException as e:
                logger.error(f"Erro na requisição: {str(e)}")
                
                if attempt < config.MAX_RETRIES - 1:
                    time.sleep(config.RETRY_DELAY)
                else:
                    raise
        
        raise Exception(f"Falha após {config.MAX_RETRIES} tentativas")
    
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
    
    def descobrir_range_nsu(self, cnpj: str) -> tuple[int, int]:
        """
        Descobre automaticamente o range de NSU que contém documentos para o CNPJ
        Usa busca binária para encontrar o primeiro e último NSU com documentos
        
        Args:
            cnpj: CNPJ do contribuinte
        
        Returns:
            Tupla (nsu_inicial, nsu_final) ou (0, 0) se não encontrar nada
        """
        # Testar ranges exponenciais para encontrar onde há documentos
        ranges_teste = [
            (0, 1000),
            (1000, 10000),
            (10000, 50000),
            (50000, 100000),
            (100000, 500000),
            (500000, 1000000),
            (1000000, 5000000)
        ]
        
        nsu_com_docs = []
        
        for inicio, fim in ranges_teste:
            # Testar alguns NSUs neste range
            nsus_teste = [inicio, (inicio + fim) // 2, fim - 1]
            
            for nsu in nsus_teste:
                # Não passar cnpj_consulta ao buscar seus próprios documentos
                logger.info(f"Testando NSU {nsu}...")
                resultado = self.buscar_por_nsu(nsu, cnpj_consulta=None, lote=True)
                time.sleep(0.5) # Pequeno delay entre buscas na descoberta
                
                if resultado:
                    status = resultado.get('StatusProcessamento')
                    logger.info(f"NSU {nsu} respondeu com status: {status}")
                
                if resultado and resultado.get('StatusProcessamento') == 'DOCUMENTOS_LOCALIZADOS':
                    nsu_com_docs.append(nsu)
                    logger.info(f"✅ Encontrado documentos no NSU {nsu}")
                    break
            
            if not nsu_com_docs:
                # Tentar NSU 1 especificamente, pois muitos começam aqui
                logger.info("Tentando NSU 1 especificamente...")
                resultado = self.buscar_por_nsu(1, cnpj_consulta=None, lote=True)
                if resultado and resultado.get('StatusProcessamento') == 'DOCUMENTOS_LOCALIZADOS':
                    nsu_com_docs.append(1)
                    logger.info("✅ Encontrados documentos começando no NSU 1")
            
            if nsu_com_docs:
                # Encontrou documentos neste range, buscar mais detalhadamente
                logger.info(f"📍 Range encontrado: {inicio} - {fim}")
                break
        
        if not nsu_com_docs:
            logger.warning("❌ Nenhum documento encontrado em nenhum range testado")
            return (0, 0)
        
        # Agora fazer busca binária para encontrar o primeiro NSU
        nsu_encontrado = nsu_com_docs[0]
        range_inicio, range_fim = ranges_teste[ranges_teste.index((inicio, fim)) if (inicio, fim) in ranges_teste else 0]
        
        # Buscar primeiro NSU (busca para trás)
        primeiro_nsu = self._buscar_primeiro_nsu(cnpj, 0, nsu_encontrado)
        
        # Buscar último NSU (busca para frente)
        ultimo_nsu = self._buscar_ultimo_nsu(cnpj, nsu_encontrado, range_fim)
        
        logger.info(f"🎯 Range descoberto: NSU {primeiro_nsu} até {ultimo_nsu}")
        return (primeiro_nsu, ultimo_nsu)
    
    def _buscar_primeiro_nsu(self, cnpj: str, inicio: int, fim: int) -> int:
        """Busca binária para encontrar o primeiro NSU com documentos"""
        if fim - inicio <= 100:
            return inicio
        
        meio = (inicio + fim) // 2
        resultado = self.buscar_por_nsu(meio, cnpj_consulta=None, lote=True)
        
        if resultado and resultado.get('StatusProcessamento') == 'DOCUMENTOS_LOCALIZADOS':
            # Há documentos no meio, buscar na primeira metade
            return self._buscar_primeiro_nsu(cnpj, inicio, meio)
        else:
            # Não há documentos no meio, buscar na segunda metade
            return self._buscar_primeiro_nsu(cnpj, meio, fim)
    
    def _buscar_ultimo_nsu(self, cnpj: str, inicio: int, fim: int) -> int:
        """Busca binária para encontrar o último NSU com documentos"""
        if fim - inicio <= 100:
            return fim
        
        meio = (inicio + fim) // 2
        resultado = self.buscar_por_nsu(meio, cnpj_consulta=None, lote=True)
        
        if resultado and resultado.get('StatusProcessamento') == 'DOCUMENTOS_LOCALIZADOS':
            # Há documentos no meio, buscar na segunda metade
            return self._buscar_ultimo_nsu(cnpj, meio, fim)
        else:
            # Não há documentos no meio, buscar na primeira metade
            return self._buscar_ultimo_nsu(cnpj, inicio, meio)
    
    def buscar_documentos_desde_nsu(self, nsu_inicial: int, cnpj: str, max_documentos: int = 500) -> List[Dict[str, Any]]:
        """
        Busca documentos fiscais de forma inteligente
        
        Se nsu_inicial for 0, faz descoberta automática do range.
        Caso contrário, busca a partir do NSU informado.
        
        Args:
            nsu_inicial: NSU inicial (0 para descoberta automática)
            cnpj: CNPJ do contribuinte
            max_documentos: Máximo de documentos a buscar
        
        Returns:
            Lista de documentos encontrados
        """
        documentos = []
        
        # Se NSU inicial é 0, descobrir automaticamente o range
        if nsu_inicial == 0:
            logger.info("🔍 NSU inicial é 0, iniciando descoberta automática...")
            primeiro_nsu, ultimo_nsu = self.descobrir_range_nsu(cnpj)
            
            if primeiro_nsu == 0 and ultimo_nsu == 0:
                logger.warning("Nenhum documento encontrado na descoberta automática")
                return []
            
            nsu_atual = primeiro_nsu
            nsu_limite = ultimo_nsu
        else:
            nsu_atual = nsu_inicial
            nsu_limite = nsu_inicial + 100000  # Limite arbitrário
        
        logger.info(f"📥 Buscando documentos de NSU {nsu_atual} até {nsu_limite}")
        
        tentativas_vazias = 0
        max_tentativas_vazias = 5
        
        while len(documentos) < max_documentos and nsu_atual <= nsu_limite and tentativas_vazias < max_tentativas_vazias:
            # Buscar lote - Não passar cnpj_consulta se for o próprio contribuinte
            resultado = self.buscar_por_nsu(nsu_atual, cnpj_consulta=None, lote=True)
            
            if not resultado:
                tentativas_vazias += 1
                nsu_atual += 1
                continue
            
            status = resultado.get('StatusProcessamento')
            
            if status == 'DOCUMENTOS_LOCALIZADOS':
                lote_dfe = resultado.get('LoteDFe', [])
                
                if not lote_dfe:
                    tentativas_vazias += 1
                    nsu_atual += 1
                    continue
                
                tentativas_vazias = 0
                
                for doc in lote_dfe:
                    documentos.append(doc)
                    doc_nsu = doc.get('NSU')
                    if doc_nsu and doc_nsu >= nsu_atual:
                        nsu_atual = doc_nsu + 1
                
                logger.info(f"✅ Lote: {len(lote_dfe)} docs | Total: {len(documentos)}")
                
                if len(lote_dfe) < 50:
                    logger.info("Lote incompleto, provavelmente fim dos documentos")
                    break
            
            elif status == 'NENHUM_DOCUMENTO_LOCALIZADO':
                tentativas_vazias += 1
                nsu_atual += 1
            
            else:
                logger.warning(f"Status: {status}")
                break
        
        logger.info(f"🎉 Busca finalizada: {len(documentos)} documentos encontrados")
        return documentos
    
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
            
            xml_gzip = base64.b64decode(arquivo_xml_base64)
            xml_content = gzip.decompress(xml_gzip).decode('utf-8')
            
            return xml_content
        
        except Exception as e:
            logger.error(f"Erro ao extrair XML: {str(e)}")
            return None
    
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
