"""
Configurações globais do sistema de download de NFS-e Nacional
"""
import os
import logging
import logging.handlers
from pathlib import Path

# Diretórios base
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
CERTIFICADOS_DIR = DATA_DIR / "certificados"
XMLS_DIR = BASE_DIR / "xmls"
LOGS_DIR = DATA_DIR / "logs"

# Criar diretórios se não existirem
DATA_DIR.mkdir(exist_ok=True)
CERTIFICADOS_DIR.mkdir(exist_ok=True)
XMLS_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# Banco de dados
DATABASE_PATH = DATA_DIR / "nfse.db"

# API NFS-e Nacional
API_BASE_URL_PRODUCAO = "https://adn.nfse.gov.br"
API_BASE_URL_HOMOLOGACAO = "https://adn.producaorestrita.nfse.gov.br"

# Ambiente: pode ser configurado via variável de ambiente NFSE_ENV (production/homologacao)
USE_PRODUCTION = os.getenv("NFSE_ENV", "production").lower() == "production"
API_BASE_URL = API_BASE_URL_PRODUCAO if USE_PRODUCTION else API_BASE_URL_HOMOLOGACAO

# Timeouts e retry (configuráveis via variáveis de ambiente)
REQUEST_TIMEOUT = int(os.getenv("NFSE_TIMEOUT", "30"))  # segundos
MAX_RETRIES = int(os.getenv("NFSE_MAX_RETRIES", "3"))
RETRY_DELAY = 2  # segundos

# Buffer de contingência NSU: volta N posições para capturar documentos atrasados
NSU_BUFFER = int(os.getenv("NFSE_NSU_BUFFER", "100"))

# Logging (configurável via variável de ambiente)
LOG_LEVEL = os.getenv("NFSE_LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# Streamlit
PAGE_TITLE = "NFS-e Nacional - Sistema de Download"
PAGE_ICON = "📄"
LAYOUT = "wide"

# Agendador automático
SCHEDULER_INTERVAL_HOURS = int(os.getenv("NFSE_SCHEDULER_HOURS", "6"))
SYNC_STATUS_DAYS = 90  # Sincronizar status de notas dos últimos N dias

# Configurações do Atualizador Automático (GitHub)
GITHUB_USERNAME = "Ramon-Leite"  # Substitua pelo seu usuário do GitHub
GITHUB_REPO = "Download-XML-NFSe"  # Substitua pelo nome do seu repositório no GitHub
GITHUB_UPDATE_URL = f"https://raw.githubusercontent.com/{GITHUB_USERNAME}/{GITHUB_REPO}/main/versao_atual.json"



def setup_logging():
    """
    Configura logging centralizado:
    - Console: formato legível para humanos
    - Arquivo: formato JSON estruturado com rotação
    """
    root_logger = logging.getLogger()
    
    # Evitar dupla configuração
    if root_logger.handlers:
        return
    
    root_logger.setLevel(getattr(logging, LOG_LEVEL))
    
    # Handler de console (formato legível)
    import sys
    if sys.stderr is not None:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(getattr(logging, LOG_LEVEL))
        console_formatter = logging.Formatter(LOG_FORMAT)
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)
    
    # Handler de arquivo com rotação (formato JSON)
    try:
        from pythonjsonlogger import jsonlogger
        
        log_file = LOGS_DIR / "nfse.log"
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=3,
            encoding='utf-8'
        )
        file_handler.setLevel(getattr(logging, LOG_LEVEL))
        
        json_formatter = jsonlogger.JsonFormatter(
            '%(asctime)s %(name)s %(levelname)s %(message)s',
            rename_fields={'asctime': 'timestamp', 'levelname': 'level'},
            datefmt='%Y-%m-%dT%H:%M:%S'
        )
        file_handler.setFormatter(json_formatter)
        root_logger.addHandler(file_handler)
        
        logging.getLogger(__name__).info(f"Logging em arquivo configurado: {log_file}")
    except ImportError:
        logging.getLogger(__name__).warning(
            "python-json-logger não instalado. Logs em arquivo JSON desativados. "
            "Instale com: pip install python-json-logger"
        )
