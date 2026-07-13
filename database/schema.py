"""
Schema do banco de dados SQLite para NFS-e Nacional
"""
import sqlite3
import logging
from pathlib import Path
import config

logger = logging.getLogger(__name__)

def init_database():
    """
    Inicializa o banco de dados criando todas as tabelas necessárias
    """
    conn = sqlite3.connect(config.DATABASE_PATH)
    cursor = conn.cursor()
    
    # Tabela de empresas
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS empresas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cnpj TEXT UNIQUE NOT NULL,
            razao_social TEXT NOT NULL,
            nome_fantasia TEXT,
            certificado_path TEXT NOT NULL,
            certificado_senha TEXT NOT NULL,
            ultimo_nsu INTEGER DEFAULT 0,
            ativo BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Tabela de NFS-e
    # A chave de acesso é única POR EMPRESA (não global): a mesma nota pode
    # pertencer a duas empresas cadastradas (uma como prestadora, outra como tomadora)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS nfse (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER NOT NULL,
            chave_acesso TEXT NOT NULL,
            numero TEXT,
            serie TEXT,
            numero_dps TEXT,
            tipo TEXT NOT NULL CHECK(tipo IN ('EMITIDA', 'RECEBIDA')),
            data_emissao DATE NOT NULL,
            data_competencia DATE,
            prestador_cnpj TEXT,
            prestador_nome TEXT,
            tomador_cnpj TEXT,
            tomador_nome TEXT,
            valor_servicos DECIMAL(15, 2),
            valor_iss DECIMAL(15, 2),
            codigo_servico TEXT,
            codigo_tributacao_nacional TEXT,
            codigo_tributacao_municipal TEXT,
            descricao_servico TEXT,
            status TEXT DEFAULT 'NORMAL' CHECK(status IN ('NORMAL', 'CANCELADA', 'SUBSTITUIDA')),
            xml_path TEXT,
            downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE,
            UNIQUE(empresa_id, chave_acesso)
        )
    """)

    # Eventos (cancelamento/substituição) que chegaram antes da respectiva nota.
    # São aplicados assim que a nota correspondente for salva.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS eventos_pendentes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chave_acesso TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('CANCELADA', 'SUBSTITUIDA')),
            recebido_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(chave_acesso, status)
        )
    """)
    
    # Tabela de logs de sincronização
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sync_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER NOT NULL,
            empresa_nome TEXT NOT NULL,
            tipo_operacao TEXT NOT NULL CHECK(tipo_operacao IN ('DOWNLOAD', 'SYNC_STATUS')),
            notas_encontradas INTEGER DEFAULT 0,
            notas_novas INTEGER DEFAULT 0,
            status_atualizados INTEGER DEFAULT 0,
            erros INTEGER DEFAULT 0,
            detalhes TEXT,
            started_at TIMESTAMP NOT NULL,
            finished_at TIMESTAMP,
            FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE
        )
    """)
    
    # Tabela de configuração do agendador (key-value)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scheduler_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    
    # Índices para melhorar performance
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_empresa_tipo 
        ON nfse(empresa_id, tipo)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_chave_acesso 
        ON nfse(chave_acesso)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_data_emissao 
        ON nfse(data_emissao)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_data_competencia 
        ON nfse(data_competencia)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_prestador_cnpj 
        ON nfse(prestador_cnpj)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_tomador_cnpj 
        ON nfse(tomador_cnpj)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sync_logs_empresa
        ON sync_logs(empresa_id, started_at DESC)
    """)
    
    conn.commit()
    conn.close()
    
    # Executar migrações para bancos existentes
    migrate()
    
    logger.info(f"✅ Banco de dados inicializado em: {config.DATABASE_PATH}")

def migrate():
    """Migra o banco de dados para a versão mais recente"""
    conn = sqlite3.connect(config.DATABASE_PATH)
    cursor = conn.cursor()
    
    # Verificar colunas existentes em nfse
    cursor.execute("PRAGMA table_info(nfse)")
    columns = [row[1] for row in cursor.fetchall()]
    
    # Adicionar codigo_tributacao_nacional se não existir
    if 'codigo_tributacao_nacional' not in columns:
        try:
            cursor.execute("ALTER TABLE nfse ADD COLUMN codigo_tributacao_nacional TEXT")
        except sqlite3.OperationalError:
            pass # Coluna já pode existir
        
    # Adicionar codigo_tributacao_municipal se não existir
    if 'codigo_tributacao_municipal' not in columns:
        try:
            cursor.execute("ALTER TABLE nfse ADD COLUMN codigo_tributacao_municipal TEXT")
        except sqlite3.OperationalError:
            pass # Coluna já pode existir
    
    # Adicionar numero_dps se não existir
    if 'numero_dps' not in columns:
        try:
            cursor.execute("ALTER TABLE nfse ADD COLUMN numero_dps TEXT")
            conn.commit()
            logger.info("Coluna numero_dps adicionada à tabela nfse")
            
            # Reprocessar XMLs existentes para popular numero_dps
            _migrar_numero_dps(cursor)
        except sqlite3.OperationalError:
            pass # Coluna já pode existir
    
    # Criar tabelas de agendamento se não existirem (migração para bancos antigos)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sync_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER NOT NULL,
            empresa_nome TEXT NOT NULL,
            tipo_operacao TEXT NOT NULL CHECK(tipo_operacao IN ('DOWNLOAD', 'SYNC_STATUS')),
            notas_encontradas INTEGER DEFAULT 0,
            notas_novas INTEGER DEFAULT 0,
            status_atualizados INTEGER DEFAULT 0,
            erros INTEGER DEFAULT 0,
            detalhes TEXT,
            started_at TIMESTAMP NOT NULL,
            finished_at TIMESTAMP,
            FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scheduler_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sync_logs_empresa
        ON sync_logs(empresa_id, started_at DESC)
    """)

    # Tabela de eventos pendentes (migração para bancos antigos)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS eventos_pendentes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chave_acesso TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('CANCELADA', 'SUBSTITUIDA')),
            recebido_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(chave_acesso, status)
        )
    """)

    conn.commit()

    # Trocar UNIQUE(chave_acesso) global por UNIQUE(empresa_id, chave_acesso)
    _migrar_dedupe_por_empresa(conn)

    conn.close()


def _migrar_dedupe_por_empresa(conn):
    """
    Bancos antigos têm chave_acesso UNIQUE global, o que impede que a mesma
    nota exista para duas empresas cadastradas (prestadora e tomadora).
    SQLite não permite alterar constraints, então a tabela é reconstruída.
    """
    cursor = conn.cursor()

    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='nfse'")
    row = cursor.fetchone()
    if not row or 'UNIQUE(empresa_id, chave_acesso)' in (row[0] or ''):
        return  # Já migrado (ou tabela inexistente)

    logger.info("Migrando tabela nfse para UNIQUE(empresa_id, chave_acesso)...")

    colunas = """id, empresa_id, chave_acesso, numero, serie, numero_dps, tipo,
            data_emissao, data_competencia, prestador_cnpj, prestador_nome,
            tomador_cnpj, tomador_nome, valor_servicos, valor_iss, codigo_servico,
            codigo_tributacao_nacional, codigo_tributacao_municipal,
            descricao_servico, status, xml_path, downloaded_at, created_at"""

    cursor.execute("PRAGMA foreign_keys=off")
    try:
        with conn:
            cursor.execute("""
                CREATE TABLE nfse_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    empresa_id INTEGER NOT NULL,
                    chave_acesso TEXT NOT NULL,
                    numero TEXT,
                    serie TEXT,
                    numero_dps TEXT,
                    tipo TEXT NOT NULL CHECK(tipo IN ('EMITIDA', 'RECEBIDA')),
                    data_emissao DATE NOT NULL,
                    data_competencia DATE,
                    prestador_cnpj TEXT,
                    prestador_nome TEXT,
                    tomador_cnpj TEXT,
                    tomador_nome TEXT,
                    valor_servicos DECIMAL(15, 2),
                    valor_iss DECIMAL(15, 2),
                    codigo_servico TEXT,
                    codigo_tributacao_nacional TEXT,
                    codigo_tributacao_municipal TEXT,
                    descricao_servico TEXT,
                    status TEXT DEFAULT 'NORMAL' CHECK(status IN ('NORMAL', 'CANCELADA', 'SUBSTITUIDA')),
                    xml_path TEXT,
                    downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE,
                    UNIQUE(empresa_id, chave_acesso)
                )
            """)
            cursor.execute(f"INSERT INTO nfse_new ({colunas}) SELECT {colunas} FROM nfse")
            cursor.execute("DROP TABLE nfse")
            cursor.execute("ALTER TABLE nfse_new RENAME TO nfse")

            # Recriar índices perdidos com o DROP
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_empresa_tipo ON nfse(empresa_id, tipo)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chave_acesso ON nfse(chave_acesso)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_data_emissao ON nfse(data_emissao)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_data_competencia ON nfse(data_competencia)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_prestador_cnpj ON nfse(prestador_cnpj)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tomador_cnpj ON nfse(tomador_cnpj)")

        logger.info("✅ Migração de dedupe por empresa concluída")
    finally:
        cursor.execute("PRAGMA foreign_keys=on")


def _migrar_numero_dps(cursor):
    """Reprocessa XMLs existentes para extrair e salvar o numero_dps"""
    from api.xml_parser import XMLParser
    
    cursor.execute("SELECT id, xml_path FROM nfse WHERE xml_path IS NOT NULL AND numero_dps IS NULL")
    rows = cursor.fetchall()
    
    if not rows:
        return
    
    logger.info(f"Migrando numero_dps para {len(rows)} notas existentes...")
    atualizados = 0
    
    for row_id, xml_path in rows:
        try:
            xml_file = Path(xml_path)
            if not xml_file.exists():
                continue
            
            xml_content = xml_file.read_text(encoding='utf-8')
            parsed = XMLParser.parse_nfse(xml_content)
            
            if parsed and not parsed.get('is_evento') and parsed.get('numero_dps'):
                cursor.execute(
                    "UPDATE nfse SET numero_dps = ? WHERE id = ?",
                    (parsed['numero_dps'], row_id)
                )
                atualizados += 1
        except Exception as e:
            logger.debug(f"Erro ao migrar nDPS da nota id={row_id}: {e}")
    
    logger.info(f"Migração de numero_dps concluída: {atualizados}/{len(rows)} notas atualizadas")

if __name__ == "__main__":
    init_database()

