"""
Corrige os caminhos dos XMLs no banco apos mover a instalacao de pasta/PC.

A tabela nfse guarda o caminho ABSOLUTO de cada arquivo .xml. Depois da
migracao para o servidor, as notas ANTIGAS continuam apontando para a pasta
da maquina antiga - o programa lista a nota (ela esta no banco), mas ao abrir
ou baixar avisa que "o XML fisico nao foi encontrado". As notas novas
funcionam porque foram gravadas ja com o caminho novo.

O script procura cada arquivo na instalacao atual, por dois caminhos:
  1. mesma estrutura <cnpj>\\<tipo>\\<ano>\\<mes>\\<arquivo> na pasta de XMLs atual;
  2. se nao achar, uma varredura pelo nome do arquivo (pega o caso classico de
     ter colado a pasta xmls DENTRO da pasta xmls, virando xmls\\xmls\\...).

Uso:
    python servidor\\corrigir_caminhos_xmls.py           (simulacao)
    python servidor\\corrigir_caminhos_xmls.py --aplicar (grava)
"""
import os
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "nfse.db"

# Quantas partes finais do caminho identificam a nota:
# <cnpj>\<emitida|recebida>\<ano>\<mes>\<arquivo>.xml
PARTES_DA_CAUDA = 5


def base_dos_xmls(conn) -> Path:
    """
    Repete a mesma regra do programa (DownloadService._base_xmls_dir):
    se houver uma pasta customizada configurada e ela existir, vale ela;
    senao, a pasta xmls\\ da instalacao.
    """
    padrao = BASE_DIR / "xmls"
    try:
        linha = conn.execute(
            "SELECT value FROM scheduler_config WHERE key = 'xmls_dir'"
        ).fetchone()
    except sqlite3.Error:
        return padrao

    if not linha or not linha[0]:
        return padrao

    customizada = linha[0]
    if os.path.exists(customizada):
        print(f"AVISO: ha uma pasta de XMLs customizada configurada e ela existe:")
        print(f"       {customizada}")
        print("       O programa vai usar ELA, e nao a pasta xmls\\ da instalacao.")
        return Path(customizada)

    print(f"AVISO: ha uma pasta de XMLs customizada configurada, mas ela NAO existe aqui:")
    print(f"       {customizada}")
    print("       (provavelmente sobrou da maquina antiga - o programa ignora e usa xmls\\)")
    print("       Vale limpar essa configuracao na tela de Configuracoes do sistema.")
    return padrao


def indexar_por_nome(base: Path) -> dict:
    """Mapeia nome_do_arquivo -> [caminhos encontrados] em toda a arvore."""
    indice = defaultdict(list)
    for raiz, _dirs, arquivos in os.walk(base):
        for arquivo in arquivos:
            if arquivo.lower().endswith(".xml"):
                indice[arquivo.lower()].append(os.path.join(raiz, arquivo))
    return indice


def cauda(caminho: str) -> tuple:
    partes = caminho.replace("/", "\\").split("\\")
    return tuple(partes[-PARTES_DA_CAUDA:])


def main():
    aplicar = "--aplicar" in sys.argv

    if not DB_PATH.exists():
        print(f"ERRO: banco nao encontrado em {DB_PATH}")
        return 1

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    print(f"Instalacao atual: {BASE_DIR}")
    base = base_dos_xmls(conn)
    print(f"Pasta de XMLs em uso: {base}")

    if not base.exists():
        print("ERRO: a pasta de XMLs nao existe. Os arquivos foram copiados para ca?")
        return 1

    notas = conn.execute(
        "SELECT id, chave_acesso, xml_path FROM nfse WHERE xml_path IS NOT NULL AND xml_path <> ''"
    ).fetchall()

    indice = None
    corrigir, ok, ausentes, ambiguos = [], 0, [], []
    aninhados = 0

    for nota in notas:
        atual = nota["xml_path"]

        if os.path.exists(atual):
            ok += 1
            continue

        # 1) mesma estrutura, so que na pasta de XMLs de agora
        candidato = base.joinpath(*cauda(atual))
        if candidato.exists():
            corrigir.append((nota["id"], str(candidato)))
            continue

        # 2) varredura pelo nome do arquivo (pasta aninhada, estrutura diferente...)
        if indice is None:
            print("Procurando os arquivos na pasta de XMLs (pode demorar um pouco)...")
            indice = indexar_por_nome(base)

        nome = os.path.basename(atual.replace("/", "\\")).lower()
        achados = indice.get(nome, [])

        if len(achados) == 1:
            corrigir.append((nota["id"], achados[0]))
            if os.path.normcase(achados[0]) != os.path.normcase(str(candidato)):
                aninhados += 1
        elif len(achados) > 1:
            # desempata por quem tem a mesma cauda (cnpj/tipo/ano/mes)
            iguais = [a for a in achados if cauda(a) == cauda(atual)]
            if len(iguais) == 1:
                corrigir.append((nota["id"], iguais[0]))
            else:
                ambiguos.append((nota["chave_acesso"], achados))
        else:
            ausentes.append((nota["chave_acesso"], atual))

    print()
    print(f"Notas com XML no banco: {len(notas)}")
    print(f"  ja corretas:  {ok}")
    print(f"  a corrigir:   {len(corrigir)}")
    print(f"  ambiguas:     {len(ambiguos)}")
    print(f"  sem arquivo:  {len(ausentes)}")

    if aninhados:
        print()
        print(f"ATENCAO: {aninhados} arquivo(s) foram achados FORA da estrutura esperada -")
        print("         tipico de ter colado a pasta xmls dentro dela mesma (xmls\\xmls\\...).")
        print("         Corrigir o banco resolve, mas o mais limpo e mover o conteudo da")
        print("         subpasta um nivel acima e rodar este script de novo.")

    if ausentes:
        print()
        print(f"Sem arquivo em disco ({len(ausentes)}) - os 5 primeiros:")
        for chave, caminho in ausentes[:5]:
            print(f"  - {chave}")
            print(f"      esperado em: {caminho}")
        print("  Esses XMLs nao foram copiados da maquina antiga, ou ficaram noutra pasta.")

    if ambiguos:
        print()
        print(f"Ambiguas ({len(ambiguos)}) - mesmo nome de arquivo em mais de um lugar:")
        for chave, achados in ambiguos[:5]:
            print(f"  - {chave}: {len(achados)} candidatos")
        print("  Nao mexi nessas para nao apontar para o arquivo errado.")

    if not aplicar:
        if corrigir:
            print()
            print("SIMULACAO - nada foi gravado.")
            print("Rode de novo com --aplicar para efetivar.")
        return 0

    if corrigir:
        with conn:
            conn.executemany(
                "UPDATE nfse SET xml_path = ? WHERE id = ?",
                [(caminho, nota_id) for nota_id, caminho in corrigir],
            )
        print()
        print(f"OK: {len(corrigir)} nota(s) reapontada(s).")
    else:
        print()
        print("Nada a corrigir.")

    conn.close()
    return 1 if (ausentes or ambiguos) else 0


if __name__ == "__main__":
    sys.exit(main())
