"""
Fiscal Manager Auto-Updater Utility
Aplica os arquivos de uma atualização de forma robusta:
- espera o programa antigo liberar os arquivos, com RETENTATIVAS por arquivo
  (resolve o antigo bug de "atualização parcial" quando um arquivo estava travado);
- NUNCA pula em silêncio: registra qualquer arquivo que não conseguir trocar;
- grava um resultado (data/temp/update_result.json) que o app lê na próxima
  inicialização para avisar o usuário se algo não foi aplicado;
- atualiza a si mesmo (updater.py) para que correções no updater cheguem aos PCs.
"""
import os
import sys
import time
import json
import zipfile
import shutil
import subprocess

# Até ~15s de espera por arquivo travado pelo processo antigo antes de desistir dele
TENTATIVAS_POR_ARQUIVO = 15
ESPERA_ENTRE_TENTATIVAS = 1.0
ESPERA_INICIAL = 3.0


def _aplicar_com_retry(src_file, dest_file):
    """Copia src->dest tolerando arquivo temporariamente travado pelo app antigo.
    Usa copy2 (sobrescreve no lugar), então uma falha nunca deixa o destino apagado."""
    ultimo_erro = None
    for _ in range(TENTATIVAS_POR_ARQUIVO):
        try:
            shutil.copy2(src_file, dest_file)
            return True, None
        except (PermissionError, OSError) as e:
            ultimo_erro = e
            time.sleep(ESPERA_ENTRE_TENTATIVAS)
    return False, ultimo_erro


def main():
    if len(sys.argv) < 2:
        return

    zip_path = sys.argv[1]
    current_dir = os.path.dirname(os.path.abspath(__file__))

    # Dá tempo do processo pai (uvicorn/pythonw) desligar e liberar os arquivos
    time.sleep(ESPERA_INICIAL)

    resultado = {"aplicados": 0, "falhas": [], "erro_geral": None}

    try:
        temp_extract_dir = os.path.join(current_dir, "data", "temp", "extracted")
        shutil.rmtree(temp_extract_dir, ignore_errors=True)  # limpa extração anterior
        os.makedirs(temp_extract_dir, exist_ok=True)

        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(temp_extract_dir)

        for root, dirs, files in os.walk(temp_extract_dir):
            relative_path = os.path.relpath(root, temp_extract_dir)

            # Nunca sobrescrever dados do usuário
            if relative_path.startswith("data") or relative_path.startswith("xmls"):
                continue

            dest_dir = current_dir if relative_path == "." else os.path.join(current_dir, relative_path)
            os.makedirs(dest_dir, exist_ok=True)

            for file in files:
                # Nunca sobrescrever bancos de dados locais
                if file.endswith(".db"):
                    continue

                src_file = os.path.join(root, file)
                dest_file = os.path.join(dest_dir, file)
                rel_file = os.path.relpath(dest_file, current_dir)

                ok, erro = _aplicar_com_retry(src_file, dest_file)
                if ok:
                    resultado["aplicados"] += 1
                else:
                    resultado["falhas"].append({"arquivo": rel_file, "erro": str(erro)})

        # Limpeza
        shutil.rmtree(temp_extract_dir, ignore_errors=True)
        try:
            if os.path.exists(zip_path):
                os.remove(zip_path)
        except Exception:
            pass

    except Exception as e:
        resultado["erro_geral"] = str(e)

    _gravar_resultado(current_dir, resultado)
    _reiniciar_app(current_dir)


def _gravar_resultado(current_dir, resultado):
    resultado["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")

    # Resultado lido pelo app na próxima inicialização (para avisar o usuário)
    try:
        status_path = os.path.join(current_dir, "data", "temp", "update_result.json")
        os.makedirs(os.path.dirname(status_path), exist_ok=True)
        with open(status_path, "w", encoding="utf-8") as f:
            json.dump(resultado, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    # Log legível em caso de qualquer problema
    if resultado["falhas"] or resultado["erro_geral"]:
        try:
            log_file = os.path.join(current_dir, "data", "logs", "updater_error.log")
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"[{resultado['timestamp']}] Atualizacao com problemas: "
                        f"{len(resultado['falhas'])} arquivo(s) nao aplicado(s); "
                        f"erro_geral={resultado['erro_geral']}\n")
                for falha in resultado["falhas"]:
                    f.write(f"    - {falha['arquivo']}: {falha['erro']}\n")
        except Exception:
            pass


def _reiniciar_app(current_dir):
    python_exe = sys.executable
    if "pythonw" in python_exe.lower():
        pass
    elif "python.exe" in python_exe.lower():
        python_exe = python_exe.replace("python.exe", "pythonw.exe")
    elif "python" in python_exe.lower():
        python_exe = python_exe.replace("python", "pythonw")

    cmd = [python_exe, "launcher.py"]
    creationflags = 0x00000008 | 0x00000200
    env = os.environ.copy()
    env["NFSE_LAUNCHER"] = "1"

    try:
        subprocess.Popen(cmd, cwd=current_dir, env=env, creationflags=creationflags, close_fds=True)
    except Exception as e:
        try:
            log_file = os.path.join(current_dir, "data", "logs", "updater_error.log")
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Falha ao reiniciar: {e}\n")
        except Exception:
            pass


if __name__ == "__main__":
    main()
