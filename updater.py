"""
Fiscal Manager Auto-Updater Utility
Executado em segundo plano de forma desacoplada para atualizar os arquivos do sistema.
"""
import os
import sys
import time
import zipfile
import shutil
import subprocess

def main():
    # Recebe o caminho do zip como argumento
    if len(sys.argv) < 2:
        return
        
    zip_path = sys.argv[1]
    
    # 1. Aguarda 2 segundos para o processo do uvicorn/pythonw pai desligar completamente e liberar os arquivos
    time.sleep(2.5)
    
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    try:
        # 2. Extrair os arquivos atualizados em pasta temporária
        temp_extract_dir = os.path.join(current_dir, "data", "temp", "extracted")
        os.makedirs(temp_extract_dir, exist_ok=True)
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_extract_dir)
            
        # 3. Mover arquivos sobrescrevendo o projeto, EXCETO a pasta 'data' (banco e chaves) e 'xmls'
        for root, dirs, files in os.walk(temp_extract_dir):
            # Calcula caminhos relativos
            relative_path = os.path.relpath(root, temp_extract_dir)
            
            # Pula pastas protegidas do usuário
            if relative_path.startswith("data") or relative_path.startswith("xmls"):
                continue
                
            dest_dir = current_dir if relative_path == "." else os.path.join(current_dir, relative_path)
            os.makedirs(dest_dir, exist_ok=True)
            
            for file in files:
                # Pula arquivos que não devem ser sobrescritos (como bancos locais ou temporários de backup)
                if file.endswith(".db") or file == "updater.py":
                    continue
                    
                src_file = os.path.join(root, file)
                dest_file = os.path.join(dest_dir, file)
                
                try:
                    # Sobrescreve
                    if os.path.exists(dest_file):
                        os.remove(dest_file)
                    shutil.move(src_file, dest_file)
                except Exception:
                    pass  # Se algum arquivo estiver travado, continua com os demais
                    
        # 4. Limpar pasta temporária e o zip
        try:
            shutil.rmtree(temp_extract_dir, ignore_errors=True)
            if os.path.exists(zip_path):
                os.remove(zip_path)
        except Exception:
            pass
            
        # 5. Reiniciar o aplicativo através do launcher em segundo plano
        python_exe = sys.executable
        if "pythonw" in python_exe.lower():
            pass
        elif "python.exe" in python_exe.lower():
            python_exe = python_exe.replace("python.exe", "pythonw.exe")
        elif "python" in python_exe.lower():
            python_exe = python_exe.replace("python", "pythonw")
            
        cmd = [python_exe, "launcher.py"]
        creationflags = 0x00000008 | 0x00000200
        
        # Define a variável de ambiente para o launcher saber que é uma reinicialização normal
        env = os.environ.copy()
        env["NFSE_LAUNCHER"] = "1"
        
        subprocess.Popen(
            cmd,
            cwd=current_dir,
            env=env,
            creationflags=creationflags,
            close_fds=True
        )
        
    except Exception as e:
        # Grava o log de erro do updater caso algo dê errado
        log_file = os.path.join(current_dir, "data", "logs", "updater_error.log")
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Erro na atualização: {str(e)}\n")

if __name__ == "__main__":
    main()
