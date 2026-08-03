"""
Corrige os caminhos dos certificados apos mover a instalacao de pasta/PC.

O banco guarda o caminho ABSOLUTO do .pfx (ex.: C:\\Users\\fulano\\...\\data\\
certificados\\12345678000199.pfx). Ao migrar para o servidor, esse caminho
deixa de existir e TODAS as empresas param de baixar nota.

Este script reaponta cada empresa para o .pfx de mesmo nome dentro da pasta
data\\certificados desta instalacao. Pode ser rodado quantas vezes quiser.

Uso:
    python servidor\\corrigir_caminhos_certificados.py           (simulacao)
    python servidor\\corrigir_caminhos_certificados.py --aplicar (grava)
"""
import os
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "nfse.db"
CERT_DIR = BASE_DIR / "data" / "certificados"


def main():
    aplicar = "--aplicar" in sys.argv

    if not DB_PATH.exists():
        print(f"ERRO: banco nao encontrado em {DB_PATH}")
        return 1

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    empresas = conn.execute(
        "SELECT id, cnpj, razao_social, certificado_path FROM empresas"
    ).fetchall()

    corrigir, ok, ausentes = [], 0, []

    for emp in empresas:
        atual = emp["certificado_path"]
        if not atual:
            continue

        # Aceita separador do Windows ou do Linux vindo de qualquer origem
        nome_arquivo = atual.replace("\\", "/").split("/")[-1]
        novo = CERT_DIR / nome_arquivo

        if not novo.exists():
            ausentes.append((emp["cnpj"], emp["razao_social"], nome_arquivo))
        # normcase: no Windows "c:\..." e "C:\..." sao o mesmo caminho
        elif os.path.normcase(str(novo)) != os.path.normcase(atual):
            corrigir.append((emp["id"], emp["cnpj"], emp["razao_social"], str(novo)))
        else:
            ok += 1

    print(f"Instalacao atual: {BASE_DIR}")
    print(f"Empresas no banco: {len(empresas)}")
    print(f"  ja corretas: {ok}")
    print(f"  a corrigir:  {len(corrigir)}")
    print(f"  sem arquivo: {len(ausentes)}")

    if ausentes:
        print("\nATENCAO - certificado nao encontrado em data\\certificados:")
        for cnpj, razao, arquivo in ausentes:
            print(f"  - {cnpj} {razao}: falta {arquivo}")
        print("  (a pasta data\\certificados foi copiada por completo?)")

    if corrigir:
        print("\nCaminhos a reapontar:")
        for _, cnpj, razao, novo in corrigir:
            print(f"  - {cnpj} {razao} -> {novo}")

    if not aplicar:
        if corrigir:
            print("\nSIMULACAO - nada foi gravado.")
            print("Rode de novo com --aplicar para efetivar.")
        return 0

    if corrigir:
        with conn:
            conn.executemany(
                "UPDATE empresas SET certificado_path = ? WHERE id = ?",
                [(novo, emp_id) for emp_id, _, _, novo in corrigir],
            )
        print(f"\nOK: {len(corrigir)} empresa(s) atualizada(s).")
    else:
        print("\nNada a fazer.")

    conn.close()
    return 1 if ausentes else 0


if __name__ == "__main__":
    sys.exit(main())
