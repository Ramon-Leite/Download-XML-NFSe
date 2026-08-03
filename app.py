"""
Aplicação Principal - Servidor FastAPI para NFS-e Nacional
Servidor REST Backend e Servidor de Arquivos Frontend SPA
"""
import sys
import os

# Garante que o Python encontre os módulos locais do projeto em ambientes embutidos/portáteis
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Se executado sob pythonw.exe (sem console), redireciona stdout/stderr para um arquivo real
# Isso evita crashes de bibliotecas que tentam interagir com os streams padrão (click, colorama, uvicorn)
if sys.stdout is None or sys.stderr is None:
    try:
        log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "stdout_stderr.log")
        # Abre o arquivo em modo de acréscimo com buffering por linha
        f = open(log_file, "a", encoding="utf-8", buffering=1)
        if sys.stdout is None:
            sys.stdout = f
        if sys.stderr is None:
            sys.stderr = f
    except Exception:
        pass

import logging
import threading
import time
import subprocess
import os
import sys
import webbrowser
import socket
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse

import config
from database import init_database
from api_routes import router as api_router

# Setup centralized logging
config.setup_logging()
logger = logging.getLogger(__name__)

# Initialize FastAPI App
app = FastAPI(
    title=config.PAGE_TITLE,
    description="Sistema de Download e Controle de NFS-e Nacional",
    version="1.0"
)

# Include API routes
app.include_router(api_router)

# Serve SPA Frontend Index
@app.get("/")
def get_index():
    index_path = config.BASE_DIR / "static" / "index.html"
    if not index_path.exists():
        # Fallback to API docs if index.html hasn't been built yet
        return RedirectResponse(url="/docs")
    return FileResponse(index_path)


# Serve Custom Favicon
@app.get("/favicon.ico")
def get_favicon():
    # Retorna o PNG em alta resolução (464x464) diretamente para o Chrome.
    # Isso força o navegador no Modo App a exibir o ícone com nitidez máxima na barra de tarefas e cabeçalho.
    png_path = config.BASE_DIR / "static" / "app_icon.png"
    if png_path.exists():
        return FileResponse(png_path, media_type="image/png")
    
    # Fallback para o arquivo .ico
    favicon_path = config.BASE_DIR / "fiscal.ico"
    if favicon_path.exists():
        return FileResponse(favicon_path)
    return FileResponse("")

# Initialize Database and Scheduler on Startup
@app.on_event("startup")
def startup_event():
    # 1. Initialize Database
    try:
        init_database()
        logger.info("Banco de dados SQLite inicializado com sucesso!")
    except Exception as e:
        logger.error(f"Erro ao inicializar banco de dados: {str(e)}")

    # 2. Initialize and Autostart Scheduler
    try:
        from services.scheduler_service import get_scheduler
        scheduler = get_scheduler()
        scheduler.auto_iniciar()
        logger.info("Agendador automático inicializado!")
    except Exception as e:
        logger.error(f"Erro ao inicializar agendador automático: {str(e)}")


# Mount static assets directory
static_dir = config.BASE_DIR / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0


def open_browser_app(url: str):
    """Abre a URL no modo App do Chrome ou Edge, ou no navegador padrão"""
    # Aguarda o servidor uvicorn subir completamente
    time.sleep(2.5)
    
    browsers = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
    ]
    
    opened = False
    for browser in browsers:
        if os.path.exists(browser):
            subprocess.Popen([browser, f"--app={url}"])
            opened = True
            break
            
    if not opened:
        webbrowser.open(url)


if __name__ == "__main__":
    # MODO SERVIDOR (NFSE_SERVIDOR=1): a máquina é o servidor do escritório.
    # Escuta em toda a rede local e NÃO abre navegador (ninguém olha a tela dela).
    # Sem a variável, o comportamento continua o de sempre: só localhost e abre o app.
    modo_servidor = os.getenv("NFSE_SERVIDOR") == "1"
    port = int(os.getenv("NFSE_PORT", "8000"))
    host = "0.0.0.0" if modo_servidor else "127.0.0.1"
    url = f"http://127.0.0.1:{port}"

    # Dispara a abertura do navegador apenas se a porta não estiver ocupada (evita abrir janelas extras no reload)
    if not modo_servidor and not is_port_in_use(port):
        threading.Thread(target=open_browser_app, args=(url,), daemon=True).start()

    # Desativa o reload automático se executado via pythonw.exe ou pelo launcher (evita travamentos/crashes em segundo plano)
    is_launcher = os.getenv("NFSE_LAUNCHER") == "1"
    is_pythonw = os.path.basename(sys.executable).lower().startswith("pythonw")
    should_reload = not (is_launcher or is_pythonw or modo_servidor)

    logger.info(f"Iniciando servidor em {host}:{port} (modo_servidor={modo_servidor}, reload={should_reload})")
    uvicorn.run("app:app", host=host, port=port, reload=should_reload)
