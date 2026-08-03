"""
Copia consistente do banco SQLite, mesmo com o sistema rodando.

Copiar o arquivo .db "na mao" enquanto o agendador escreve pode gerar um
arquivo corrompido (ainda mais em modo WAL). A API de backup do proprio
SQLite resolve isso: ela tira um snapshot integro sem parar o servidor.

Uso:  python backup_db.py <pasta_destino> [dias_de_retencao]
"""
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "nfse.db"
RETENCAO_PADRAO = 30


def copiar_banco(destino: Path) -> Path:
    destino.mkdir(parents=True, exist_ok=True)
    arquivo = destino / f"nfse_{datetime.now():%Y-%m-%d}.db"

    origem = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=30)
    try:
        copia = sqlite3.connect(arquivo)
        try:
            origem.backup(copia)
        finally:
            copia.close()
    finally:
        origem.close()

    return arquivo


def limpar_antigos(destino: Path, dias: int) -> int:
    limite = time.time() - dias * 86400
    removidos = 0
    for antigo in destino.glob("nfse_*.db"):
        if antigo.stat().st_mtime < limite:
            antigo.unlink()
            removidos += 1
    return removidos


def main():
    if len(sys.argv) < 2:
        print("Uso: python backup_db.py <pasta_destino> [dias_de_retencao]")
        return 1

    destino = Path(sys.argv[1])
    dias = int(sys.argv[2]) if len(sys.argv) > 2 else RETENCAO_PADRAO

    if not DB_PATH.exists():
        print(f"ERRO: banco nao encontrado em {DB_PATH}")
        return 1

    try:
        arquivo = copiar_banco(destino)
    except sqlite3.Error as e:
        print(f"ERRO ao copiar o banco: {e}")
        return 1

    tamanho_mb = arquivo.stat().st_size / (1024 * 1024)
    print(f"OK: {arquivo} ({tamanho_mb:.1f} MB)")

    removidos = limpar_antigos(destino, dias)
    if removidos:
        print(f"Limpeza: {removidos} copia(s) com mais de {dias} dias removida(s)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
