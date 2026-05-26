import os
import sys
import time
import subprocess
import socket
import webbrowser

# Se executado sob pythonw.exe (sem console), redireciona stdout/stderr para evitar crashes de prints
if sys.stdout is None or sys.stderr is None:
    try:
        log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "launcher_stdout_stderr.log")
        f = open(log_file, "a", encoding="utf-8", buffering=1)
        if sys.stdout is None:
            sys.stdout = f
        if sys.stderr is None:
            sys.stderr = f
    except Exception:
        pass

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def start_fastapi():
    """Inicia o servidor FastAPI em um processo pythonw.exe oculto e desvinculado"""
    import sys
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Usa pythonw.exe para evitar consoles e garantir a sobrevivência em segundo plano
    python_exe = sys.executable
    if "python.exe" in python_exe.lower() and "pythonw.exe" not in python_exe.lower():
        python_exe = python_exe.replace("python.exe", "pythonw.exe")
    elif "python" in python_exe.lower() and "pythonw" not in python_exe.lower():
        # Caso seja apenas 'python', tenta mapear para 'pythonw'
        python_exe = python_exe.replace("python", "pythonw")
    
    # Define a variável de ambiente para indicar que está sendo iniciado pelo launcher
    env = os.environ.copy()
    env["NFSE_LAUNCHER"] = "1"
    
    cmd = [python_exe, "app.py"]
    
    # Combinação de flags avançadas:
    # 0x00000008 (DETACHED_PROCESS) - Desvincula do console pai
    # 0x00000200 (CREATE_NEW_PROCESS_GROUP) - Coloca o subprocesso em um grupo de processos independente
    # 0x01000000 (CREATE_BREAKAWAY_FROM_JOB) - Rompe vínculos com Job Objects do pai
    try:
        creationflags = 0x00000008 | 0x00000200 | 0x01000000
        return subprocess.Popen(
            cmd,
            cwd=current_dir,
            env=env,
            creationflags=creationflags,
            close_fds=True
        )
    except PermissionError:
        # Fallback caso o ambiente restrinja breakaway de Jobs (como em sandboxes ou certas permissões)
        creationflags = 0x00000008 | 0x00000200
        return subprocess.Popen(
            cmd,
            cwd=current_dir,
            env=env,
            creationflags=creationflags,
            close_fds=True
        )

def open_as_app(url):
    """Tenta abrir a URL no modo App do Chrome ou Edge"""
    # Caminhos comuns do Chrome e Edge
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
        # Se não achar Chrome/Edge, abre no navegador padrão mesmo
        webbrowser.open(url)

def main():
    port = 8000
    
    # 1. Se a porta já está em uso, apenas abre o navegador e sai
    if is_port_in_use(port):
        print("Servidor já está rodando. Abrindo aplicativo...")
        open_as_app(f"http://localhost:{port}")
        return
    
    # 2. Se não está em uso, inicia o servidor. O próprio app.py vai abrir o navegador!
    print("Iniciando servidor...")
    start_fastapi()

if __name__ == "__main__":
    main()
