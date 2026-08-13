"""
Repositórios para acesso aos dados no banco SQLite
"""
import sqlite3
import logging
from typing import List, Optional, Tuple
from datetime import date, datetime
from decimal import Decimal
import config
from .models import Empresa, NFSe, SyncLog

logger = logging.getLogger(__name__)

# Campos de data válidos para uso em queries (whitelist contra SQL injection)
VALID_DATE_FIELDS = {'data_emissao', 'data_competencia'}

# Tempo que uma escrita espera o banco ser liberado antes de falhar com "database is locked".
# Necessário no modo servidor: vários navegadores + o agendador escrevem ao mesmo tempo.
BUSY_TIMEOUT_MS = 10000


def _conectar(db_path) -> sqlite3.Connection:
    """Abre conexão com o banco já configurada para uso multiusuário."""
    conn = sqlite3.connect(db_path, timeout=BUSY_TIMEOUT_MS / 1000)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    return conn


def _dec(row: sqlite3.Row, coluna: str) -> Optional[Decimal]:
    """
    Lê uma coluna numérica opcional. Tolera a coluna ainda não existir para o
    caso do banco ser lido antes da migração ter rodado.
    """
    if coluna not in row.keys():
        return None
    valor = row[coluna]
    return Decimal(str(valor)) if valor is not None else None


class EmpresaRepository:
    """Repositório para operações com empresas"""
    
    def __init__(self):
        self.db_path = config.DATABASE_PATH
    
    def _get_connection(self) -> sqlite3.Connection:
        """Cria conexão com o banco"""
        conn = _conectar(self.db_path)
        return conn
    
    def create(self, empresa: Empresa) -> int:
        """Cria uma nova empresa"""
        conn = self._get_connection()
        try:
            with conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO empresas (cnpj, razao_social, nome_fantasia, certificado_path, certificado_senha, ultimo_nsu, ativo)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (empresa.cnpj, empresa.razao_social, empresa.nome_fantasia, 
                      empresa.certificado_path, empresa.certificado_senha, empresa.ultimo_nsu, empresa.ativo))
                return cursor.lastrowid
        finally:
            conn.close()
    
    def get_by_id(self, empresa_id: int) -> Optional[Empresa]:
        """Busca empresa por ID"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM empresas WHERE id = ?", (empresa_id,))
            row = cursor.fetchone()
            
            if row:
                return self._row_to_empresa(row)
            return None
        finally:
            conn.close()
    
    def get_by_cnpj(self, cnpj: str) -> Optional[Empresa]:
        """Busca empresa por CNPJ"""
        cnpj_limpo = ''.join(filter(str.isdigit, cnpj))
        
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM empresas WHERE cnpj = ?", (cnpj_limpo,))
            row = cursor.fetchone()
            
            if row:
                return self._row_to_empresa(row)
            return None
        finally:
            conn.close()
    
    def get_all(self, apenas_ativas: bool = True) -> List[Empresa]:
        """Lista todas as empresas"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            if apenas_ativas:
                cursor.execute("SELECT * FROM empresas WHERE ativo = 1 ORDER BY razao_social")
            else:
                cursor.execute("SELECT * FROM empresas ORDER BY razao_social")
            
            rows = cursor.fetchall()
            return [self._row_to_empresa(row) for row in rows]
        finally:
            conn.close()
    
    def update(self, empresa: Empresa) -> bool:
        """Atualiza uma empresa"""
        conn = self._get_connection()
        try:
            with conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE empresas 
                    SET razao_social = ?, nome_fantasia = ?, certificado_path = ?, 
                        certificado_senha = ?, ultimo_nsu = ?, ativo = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (empresa.razao_social, empresa.nome_fantasia, empresa.certificado_path,
                      empresa.certificado_senha, empresa.ultimo_nsu, empresa.ativo, empresa.id))
                return cursor.rowcount > 0
        finally:
            conn.close()
    
    def delete(self, empresa_id: int) -> bool:
        """Deleta uma empresa"""
        conn = self._get_connection()
        try:
            with conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM empresas WHERE id = ?", (empresa_id,))
                return cursor.rowcount > 0
        finally:
            conn.close()
    
    def _row_to_empresa(self, row: sqlite3.Row) -> Empresa:
        """Converte row do banco para objeto Empresa"""
        return Empresa(
            id=row['id'],
            cnpj=row['cnpj'],
            razao_social=row['razao_social'],
            nome_fantasia=row['nome_fantasia'],
            certificado_path=row['certificado_path'],
            certificado_senha=row['certificado_senha'],
            ultimo_nsu=row['ultimo_nsu'] if 'ultimo_nsu' in row.keys() else 0,
            ativo=bool(row['ativo']),
            created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
            updated_at=datetime.fromisoformat(row['updated_at']) if row['updated_at'] else None
        )


class NFSeRepository:
    """Repositório para operações com NFS-e"""
    
    def __init__(self):
        self.db_path = config.DATABASE_PATH
    
    def _get_connection(self) -> sqlite3.Connection:
        """Cria conexão com o banco"""
        conn = _conectar(self.db_path)
        return conn
    
    def create(self, nfse: NFSe) -> int:
        """Cria uma nova NFS-e"""
        conn = self._get_connection()
        try:
            with conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO nfse (
                        empresa_id, chave_acesso, numero, serie, numero_dps, tipo, data_emissao, data_competencia,
                        prestador_cnpj, prestador_nome, tomador_cnpj, tomador_nome,
                        valor_servicos, valor_iss, iss_retido, ret_pis, ret_cofins,
                        ret_irrf, ret_csll, ret_inss, valor_retencoes,
                        codigo_servico, codigo_tributacao_nacional,
                        codigo_tributacao_municipal, descricao_servico, status, xml_path
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    nfse.empresa_id, nfse.chave_acesso, nfse.numero, nfse.serie, nfse.numero_dps, nfse.tipo,
                    nfse.data_emissao, nfse.data_competencia, nfse.prestador_cnpj, nfse.prestador_nome,
                    nfse.tomador_cnpj, nfse.tomador_nome,
                    float(nfse.valor_servicos) if nfse.valor_servicos else 0.0,
                    float(nfse.valor_iss) if nfse.valor_iss else 0.0,
                    float(nfse.iss_retido or 0), float(nfse.ret_pis or 0),
                    float(nfse.ret_cofins or 0), float(nfse.ret_irrf or 0),
                    float(nfse.ret_csll or 0), float(nfse.ret_inss or 0),
                    float(nfse.valor_retencoes or 0),
                    nfse.codigo_servico, nfse.codigo_tributacao_nacional,
                    nfse.codigo_tributacao_municipal, nfse.descricao_servico, nfse.status, nfse.xml_path
                ))
                return cursor.lastrowid
        finally:
            conn.close()
    
    def get_by_chave(self, chave_acesso: str, empresa_id: Optional[int] = None) -> Optional[NFSe]:
        """Busca NFS-e por chave de acesso (opcionalmente restrita a uma empresa)"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            if empresa_id is not None:
                cursor.execute(
                    "SELECT * FROM nfse WHERE chave_acesso = ? AND empresa_id = ?",
                    (chave_acesso, empresa_id)
                )
            else:
                cursor.execute("SELECT * FROM nfse WHERE chave_acesso = ?", (chave_acesso,))
            row = cursor.fetchone()

            if row:
                return self._row_to_nfse(row)
            return None
        finally:
            conn.close()

    def get_all_by_chave(self, chave_acesso: str) -> List[NFSe]:
        """Busca TODAS as NFS-e com a chave (a mesma nota pode existir para mais de uma empresa)"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM nfse WHERE chave_acesso = ?", (chave_acesso,))
            return [self._row_to_nfse(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def exists_by_chave(self, chave_acesso: str, empresa_id: Optional[int] = None) -> bool:
        """Verifica se NFS-e já existe (otimizado com SELECT 1). Com empresa_id, restringe à empresa."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            if empresa_id is not None:
                cursor.execute(
                    "SELECT 1 FROM nfse WHERE chave_acesso = ? AND empresa_id = ? LIMIT 1",
                    (chave_acesso, empresa_id)
                )
            else:
                cursor.execute("SELECT 1 FROM nfse WHERE chave_acesso = ? LIMIT 1", (chave_acesso,))
            return cursor.fetchone() is not None
        finally:
            conn.close()
    
    def get_all(self, empresa_id: Optional[int] = None, tipo: Optional[str] = None,
                status: Optional[str] = None,
                data_inicio: Optional[date] = None, data_fim: Optional[date] = None,
                campo_data: str = 'data_emissao', texto_busca: Optional[str] = None) -> List[NFSe]:
        """
        Lista NFS-e com filtros
        
        Args:
            empresa_id: Filtrar por empresa
            tipo: Filtrar por tipo (EMITIDA/RECEBIDA)
            status: Filtrar por status (NORMAL/CANCELADA/SUBSTITUIDA)
            data_inicio: Data inicial
            data_fim: Data final
            campo_data: Campo de data para filtrar (data_emissao ou data_competencia)
            texto_busca: Texto para busca em número, prestador, tomador e descrição
        """
        # Validação whitelist contra SQL injection
        if campo_data not in VALID_DATE_FIELDS:
            raise ValueError(f"Campo de data inválido: '{campo_data}'. Valores permitidos: {VALID_DATE_FIELDS}")
        
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            query = "SELECT * FROM nfse WHERE 1=1"
            params = []
            
            if empresa_id:
                query += " AND empresa_id = ?"
                params.append(empresa_id)
            
            if tipo:
                query += " AND tipo = ?"
                params.append(tipo)
            
            if status:
                query += " AND status = ?"
                params.append(status)
            
            if data_inicio:
                query += f" AND {campo_data} >= ?"
                params.append(data_inicio)
            
            if data_fim:
                query += f" AND {campo_data} <= ?"
                params.append(data_fim)
            
            if texto_busca:
                texto_like = f"%{texto_busca}%"
                query += """ AND (
                    numero LIKE ? OR
                    numero_dps LIKE ? OR
                    prestador_nome LIKE ? OR
                    prestador_cnpj LIKE ? OR
                    tomador_nome LIKE ? OR
                    tomador_cnpj LIKE ? OR
                    descricao_servico LIKE ?
                )"""
                params.extend([texto_like] * 7)
            
            query += f" ORDER BY {campo_data} DESC"
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            return [self._row_to_nfse(row) for row in rows]
        finally:
            conn.close()
    
    def count_all(self, empresa_id: Optional[int] = None) -> int:
        """Conta total de NFS-e"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            if empresa_id:
                cursor.execute("SELECT COUNT(*) FROM nfse WHERE empresa_id = ?", (empresa_id,))
            else:
                cursor.execute("SELECT COUNT(*) FROM nfse")
            
            count = cursor.fetchone()[0]
            return count
        finally:
            conn.close()
    
    def get_statistics(self, empresa_id: Optional[int] = None) -> dict:
        """Retorna estatísticas de NFS-e"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            where_clause = "WHERE empresa_id = ?" if empresa_id else ""
            params = (empresa_id,) if empresa_id else ()
            
            cursor.execute(f"""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN tipo = 'EMITIDA' THEN 1 ELSE 0 END) as total_emitidas,
                    SUM(CASE WHEN tipo = 'RECEBIDA' THEN 1 ELSE 0 END) as total_recebidas,
                    SUM(CASE WHEN tipo = 'EMITIDA' THEN valor_servicos ELSE 0 END) as valor_total_emitido,
                    SUM(CASE WHEN tipo = 'RECEBIDA' THEN valor_servicos ELSE 0 END) as valor_total_recebido
                FROM nfse {where_clause}
            """, params)
            
            row = cursor.fetchone()
            
            return {
                'total': row['total'] or 0,
                'total_emitidas': row['total_emitidas'] or 0,
                'total_recebidas': row['total_recebidas'] or 0,
                'valor_total_emitido': Decimal(str(row['valor_total_emitido'] or 0)),
                'valor_total_recebido': Decimal(str(row['valor_total_recebido'] or 0))
            }
        finally:
            conn.close()
    
    def update(self, nfse: NFSe) -> bool:
        """Atualiza uma NFS-e existente"""
        conn = self._get_connection()
        try:
            with conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE nfse 
                    SET prestador_cnpj = ?, prestador_nome = ?, 
                        tomador_cnpj = ?, tomador_nome = ?,
                        valor_servicos = ?, valor_iss = ?,
                        codigo_servico = ?, codigo_tributacao_nacional = ?,
                        codigo_tributacao_municipal = ?, descricao_servico = ?,
                        status = ?, numero = ?, serie = ?, numero_dps = ?,
                        data_emissao = ?, data_competencia = ?,
                        xml_path = ?
                    WHERE id = ?
                """, (
                    nfse.prestador_cnpj, nfse.prestador_nome,
                    nfse.tomador_cnpj, nfse.tomador_nome,
                    float(nfse.valor_servicos) if nfse.valor_servicos else 0.0,
                    float(nfse.valor_iss) if nfse.valor_iss else 0.0,
                    nfse.codigo_servico, nfse.codigo_tributacao_nacional,
                    nfse.codigo_tributacao_municipal, nfse.descricao_servico,
                    nfse.status, nfse.numero, nfse.serie, nfse.numero_dps,
                    nfse.data_emissao, nfse.data_competencia,
                    nfse.xml_path,
                    nfse.id
                ))
                return cursor.rowcount > 0
        finally:
            conn.close()
    
    def _row_to_nfse(self, row: sqlite3.Row) -> NFSe:
        """Converte row do banco para objeto NFSe"""
        return NFSe(
            id=row['id'],
            empresa_id=row['empresa_id'],
            chave_acesso=row['chave_acesso'],
            numero=row['numero'],
            serie=row['serie'],
            numero_dps=row['numero_dps'] if 'numero_dps' in row.keys() else None,
            tipo=row['tipo'],
            data_emissao=date.fromisoformat(row['data_emissao']) if row['data_emissao'] else None,
            data_competencia=date.fromisoformat(row['data_competencia']) if row['data_competencia'] else None,
            prestador_cnpj=row['prestador_cnpj'],
            prestador_nome=row['prestador_nome'],
            tomador_cnpj=row['tomador_cnpj'],
            tomador_nome=row['tomador_nome'],
            valor_servicos=Decimal(str(row['valor_servicos'])) if row['valor_servicos'] else None,
            valor_iss=Decimal(str(row['valor_iss'])) if row['valor_iss'] else None,
            iss_retido=_dec(row, 'iss_retido'),
            ret_pis=_dec(row, 'ret_pis'),
            ret_cofins=_dec(row, 'ret_cofins'),
            ret_irrf=_dec(row, 'ret_irrf'),
            ret_csll=_dec(row, 'ret_csll'),
            ret_inss=_dec(row, 'ret_inss'),
            valor_retencoes=_dec(row, 'valor_retencoes'),
            codigo_servico=row['codigo_servico'],
            codigo_tributacao_nacional=row['codigo_tributacao_nacional'] if 'codigo_tributacao_nacional' in row.keys() else None,
            codigo_tributacao_municipal=row['codigo_tributacao_municipal'] if 'codigo_tributacao_municipal' in row.keys() else None,
            descricao_servico=row['descricao_servico'],
            status=row['status'],
            xml_path=row['xml_path'],
            downloaded_at=datetime.fromisoformat(row['downloaded_at']) if row['downloaded_at'] else None,
            created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None
        )


    def detectar_gaps_dps(self, empresa_id: int) -> List[dict]:
        """
        Detecta lacunas na numeração de DPS das notas EMITIDAS, por série.

        Diferente da chave de acesso (que tem código aleatório), o id da DPS
        é derivável — então lacunas de DPS podem ser buscadas ativamente na
        SEFIN Nacional.

        Considera TODOS os status (nota cancelada também ocupa número).
        O código do município é extraído da chave de acesso das notas já
        baixadas (7 primeiros dígitos da chave de 50 posições).

        Returns:
            Lista de dicts: {'serie', 'cmun', 'faltantes', 'primeiro', 'ultimo'}
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT numero_dps, serie, chave_acesso FROM nfse
                WHERE empresa_id = ? AND tipo = 'EMITIDA'
                AND numero_dps IS NOT NULL
            """, (empresa_id,))
            rows = cursor.fetchall()
        finally:
            conn.close()

        # Agrupar por série
        series = {}
        for row in rows:
            try:
                ndps = int(row['numero_dps'])
            except (ValueError, TypeError):
                continue

            serie = (row['serie'] or '').strip() or '1'
            grupo = series.setdefault(serie, {'numeros': set(), 'cmun': None})
            grupo['numeros'].add(ndps)

            # Extrair código do município da chave de acesso (50 dígitos)
            chave = (row['chave_acesso'] or '').strip()
            if grupo['cmun'] is None and len(chave) == 50 and chave.isdigit():
                grupo['cmun'] = chave[:7]

        resultado = []
        for serie, grupo in series.items():
            numeros = sorted(grupo['numeros'])
            if len(numeros) < 2 or not grupo['cmun']:
                continue

            primeiro, ultimo = numeros[0], numeros[-1]
            conjunto = grupo['numeros']
            faltantes = [n for n in range(primeiro, ultimo + 1) if n not in conjunto]

            if faltantes:
                resultado.append({
                    'serie': serie,
                    'cmun': grupo['cmun'],
                    'faltantes': faltantes,
                    'primeiro': primeiro,
                    'ultimo': ultimo
                })

        return resultado

    def detectar_gaps_numeracao(self, empresa_id: int) -> dict:
        """
        Detecta gaps na numeração de NFS-e emitidas de uma empresa.
        Retorna dict com: numeros_faltantes, primeiro_numero, ultimo_numero, total_notas

        Considera TODOS os status: uma nota cancelada ou substituída existe e
        ocupa o seu número — não é uma nota "faltante". Filtrar por status aqui
        criaria falsos gaps no lugar dessas notas.
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT numero FROM nfse
                WHERE empresa_id = ? AND tipo = 'EMITIDA'
                AND numero IS NOT NULL
                ORDER BY CAST(numero AS INTEGER)
            """, (empresa_id,))
            rows = cursor.fetchall()
            
            if not rows:
                return {'numeros_faltantes': [], 'primeiro': 0, 'ultimo': 0, 'total': 0}
            
            # Converter para inteiros (ignorar números não-numéricos)
            numeros = []
            for row in rows:
                try:
                    numeros.append(int(row['numero']))
                except (ValueError, TypeError):
                    continue
            
            if not numeros:
                return {'numeros_faltantes': [], 'primeiro': 0, 'ultimo': 0, 'total': 0}
            
            numeros.sort()
            primeiro = numeros[0]
            ultimo = numeros[-1]
            
            # Detectar gaps
            conjunto = set(numeros)
            faltantes = [n for n in range(primeiro, ultimo + 1) if n not in conjunto]
            
            return {
                'numeros_faltantes': faltantes,
                'primeiro': primeiro,
                'ultimo': ultimo,
                'total': len(numeros)
            }
        finally:
            conn.close()


class SyncLogRepository:
    """Repositório para logs de sincronização automática"""
    
    def __init__(self):
        self.db_path = config.DATABASE_PATH
    
    def _get_connection(self) -> sqlite3.Connection:
        conn = _conectar(self.db_path)
        return conn
    
    def create(self, log: SyncLog) -> int:
        """Cria um novo registro de sync"""
        conn = self._get_connection()
        try:
            with conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO sync_logs (
                        empresa_id, empresa_nome, tipo_operacao,
                        notas_encontradas, notas_novas, status_atualizados,
                        erros, detalhes, started_at, finished_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    log.empresa_id, log.empresa_nome, log.tipo_operacao,
                    log.notas_encontradas, log.notas_novas, log.status_atualizados,
                    log.erros, log.detalhes, log.started_at, log.finished_at
                ))
                return cursor.lastrowid
        finally:
            conn.close()
    
    def get_recent(self, limit: int = 50) -> List[SyncLog]:
        """Retorna os logs mais recentes"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM sync_logs ORDER BY started_at DESC LIMIT ?",
                (limit,)
            )
            rows = cursor.fetchall()
            return [self._row_to_sync_log(row) for row in rows]
        finally:
            conn.close()
    
    def _row_to_sync_log(self, row: sqlite3.Row) -> SyncLog:
        return SyncLog(
            id=row['id'],
            empresa_id=row['empresa_id'],
            empresa_nome=row['empresa_nome'],
            tipo_operacao=row['tipo_operacao'],
            notas_encontradas=row['notas_encontradas'],
            notas_novas=row['notas_novas'],
            status_atualizados=row['status_atualizados'],
            erros=row['erros'],
            detalhes=row['detalhes'],
            started_at=datetime.fromisoformat(row['started_at']) if row['started_at'] else None,
            finished_at=datetime.fromisoformat(row['finished_at']) if row['finished_at'] else None
        )


class SchedulerConfigRepository:
    """Repositório para configuração do agendador (key-value)"""
    
    def __init__(self):
        self.db_path = config.DATABASE_PATH
    
    def _get_connection(self) -> sqlite3.Connection:
        conn = _conectar(self.db_path)
        return conn
    
    def get(self, key: str, default: str = None) -> Optional[str]:
        """Retorna valor de uma configuração"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM scheduler_config WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row['value'] if row else default
        finally:
            conn.close()
    
    def set(self, key: str, value: str) -> None:
        """Define valor de uma configuração (insert or replace)"""
        conn = self._get_connection()
        try:
            with conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR REPLACE INTO scheduler_config (key, value) VALUES (?, ?)",
                    (key, value)
                )
        finally:
            conn.close()


class EventoPendenteRepository:
    """
    Repositório para eventos (cancelamento/substituição) que chegaram na
    distribuição ANTES da respectiva nota. Ficam guardados e são aplicados
    assim que a nota correspondente for salva.
    """

    def __init__(self):
        self.db_path = config.DATABASE_PATH

    def _get_connection(self) -> sqlite3.Connection:
        conn = _conectar(self.db_path)
        return conn

    def add(self, chave_acesso: str, status: str) -> None:
        """Registra um evento pendente (idempotente)"""
        conn = self._get_connection()
        try:
            with conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR IGNORE INTO eventos_pendentes (chave_acesso, status) VALUES (?, ?)",
                    (chave_acesso, status)
                )
        finally:
            conn.close()

    def get_by_chave(self, chave_acesso: str) -> List[str]:
        """Retorna os status pendentes para uma chave (mais recente por último)"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT status FROM eventos_pendentes WHERE chave_acesso = ? ORDER BY recebido_em, id",
                (chave_acesso,)
            )
            return [row['status'] for row in cursor.fetchall()]
        finally:
            conn.close()

    def delete_by_chave(self, chave_acesso: str) -> None:
        """Remove os eventos pendentes de uma chave (após aplicados)"""
        conn = self._get_connection()
        try:
            with conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM eventos_pendentes WHERE chave_acesso = ?", (chave_acesso,))
        finally:
            conn.close()

