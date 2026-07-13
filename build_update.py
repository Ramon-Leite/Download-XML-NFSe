"""
Gera o update.zip completo para distribuição via GitHub Releases.

Empacota um SNAPSHOT COMPLETO do código do sistema (não apenas os arquivos
alterados), garantindo que o outro PC sempre receba uma versão consistente —
elimina a classe de bug "esqueci de incluir um arquivo interdependente".

Nunca inclui dados do usuário (data/, xmls/) nem artefatos de desenvolvimento.
Ao final, valida que todos os arquivos críticos entraram no pacote; se faltar
algum, o build é abortado (melhor falhar aqui do que quebrar o outro PC).

Uso:
    python build_update.py
"""
import os
import zipfile
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
OUTPUT = BASE_DIR / "update.zip"

# Pastas que nunca entram no pacote (dados do usuário e artefatos de dev).
# A verificação é por nome de pasta, em qualquer nível.
EXCLUDE_DIRS = {
    "data", "xmls", "tests", ".claude", ".git", "__pycache__",
    ".pytest_cache", ".vscode", ".idea", "node_modules", ".mypy_cache",
}
# Arquivos que nunca entram no pacote
EXCLUDE_FILE_SUFFIXES = (".db", ".db.bak", ".pyc", ".log", ".pyo")
EXCLUDE_FILE_NAMES = {"update.zip"}

# Arquivos que OBRIGATORIAMENTE precisam estar no pacote. Se algum faltar,
# o outro PC quebraria na inicialização — então o build falha alto.
ARQUIVOS_CRITICOS = [
    "app.py", "api_routes.py", "config.py", "launcher.py", "updater.py",
    "requirements.txt", "versao_atual.json",
    "api/__init__.py", "api/nfse_client.py", "api/certificate_manager.py",
    "api/xml_parser.py",
    "database/__init__.py", "database/schema.py", "database/repository.py",
    "database/models.py",
    "services/__init__.py", "services/download_service.py",
    "services/scheduler_service.py", "services/empresa_service.py",
    "services/backup_service.py",
    "static/index.html", "static/style.css", "static/app.js",
]


def main():
    if OUTPUT.exists():
        OUTPUT.unlink()

    incluidos = []
    with zipfile.ZipFile(OUTPUT, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(BASE_DIR):
            # Poda pastas excluídas in-place para não descer nelas (.git, data...)
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for file in files:
                path = Path(root) / file
                if path.name in EXCLUDE_FILE_NAMES:
                    continue
                if path.suffix.lower() in EXCLUDE_FILE_SUFFIXES:
                    continue
                # Caminho relativo com "/" (compatível entre Windows e o updater)
                arcname = path.relative_to(BASE_DIR).as_posix()
                z.write(path, arcname)
                incluidos.append(arcname)

    incluidos_set = set(incluidos)
    faltando = [f for f in ARQUIVOS_CRITICOS if f not in incluidos_set]
    if faltando:
        OUTPUT.unlink()
        raise SystemExit(
            "ERRO: arquivos criticos ausentes do pacote (build abortado):\n  "
            + "\n  ".join(faltando)
        )

    tamanho_kb = OUTPUT.stat().st_size / 1024
    print(f"OK: update.zip gerado com {len(incluidos)} arquivos ({tamanho_kb:.0f} KB)")
    print(f"Local: {OUTPUT}")
    print()
    print("Antes de publicar o Release no GitHub, confirme que as versoes batem:")
    print("  - versao_atual.json -> 'versao' e 'url_download' (aponta pro novo Release)")
    print("  - api_routes.py     -> versao_local (mesma versao)")


if __name__ == "__main__":
    main()
