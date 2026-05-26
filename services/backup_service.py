"""
Serviço para backup e restauração do banco de dados e XMLs
"""
import logging
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional
import config

logger = logging.getLogger(__name__)


class BackupService:
    """Gerencia backup e restauração do sistema"""
    
    def __init__(self):
        self.backups_dir = config.DATA_DIR / "backups"
        self.backups_dir.mkdir(exist_ok=True)
    
    def criar_backup(self, callback=None) -> Path:
        """
        Cria backup do banco de dados e dos XMLs em um arquivo ZIP.
        
        Args:
            callback: Função de callback para progresso (opcional)
        
        Returns:
            Path do arquivo ZIP criado
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_filename = f"backup_{timestamp}.zip"
        zip_path = self.backups_dir / zip_filename
        
        if callback:
            callback("Iniciando backup...")
        
        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                # 1. Backup do banco de dados
                db_path = config.DATABASE_PATH
                if db_path.exists():
                    if callback:
                        callback("Salvando banco de dados...")
                    zf.write(db_path, f"data/{db_path.name}")
                    logger.info(f"Banco de dados adicionado ao backup: {db_path.name}")
                
                # 2. Backup dos XMLs
                xmls_dir = config.XMLS_DIR
                if xmls_dir.exists():
                    xml_files = list(xmls_dir.rglob("*.xml"))
                    total_xmls = len(xml_files)
                    
                    if callback:
                        callback(f"Salvando {total_xmls} arquivos XML...")
                    
                    for i, xml_file in enumerate(xml_files):
                        # Manter a estrutura de diretórios relativa
                        arcname = f"xmls/{xml_file.relative_to(xmls_dir)}"
                        zf.write(xml_file, arcname)
                        
                        if callback and i % 50 == 0 and total_xmls > 0:
                            callback(f"Salvando XMLs... {i+1}/{total_xmls}")
                    
                    logger.info(f"{total_xmls} arquivos XML adicionados ao backup")
            
            tamanho_mb = zip_path.stat().st_size / (1024 * 1024)
            logger.info(f"Backup criado: {zip_path} ({tamanho_mb:.1f} MB)")
            
            if callback:
                callback(f"✅ Backup concluído: {zip_filename} ({tamanho_mb:.1f} MB)")
            
            return zip_path
            
        except Exception as e:
            logger.error(f"Erro ao criar backup: {e}")
            # Remover ZIP incompleto se existir
            if zip_path.exists():
                zip_path.unlink()
            raise
    
    def restaurar_backup(self, zip_path: str, callback=None) -> dict:
        """
        Restaura backup a partir de um arquivo ZIP.
        
        Args:
            zip_path: Caminho do arquivo ZIP
            callback: Função de callback para progresso (opcional)
        
        Returns:
            Dicionário com estatísticas da restauração
        """
        zip_path = Path(zip_path)
        stats = {'banco_restaurado': False, 'xmls_restaurados': 0}
        
        if not zip_path.exists():
            raise FileNotFoundError(f"Arquivo de backup não encontrado: {zip_path}")
        
        if not zipfile.is_zipfile(zip_path):
            raise ValueError("Arquivo inválido: não é um ZIP válido")
        
        if callback:
            callback("Verificando arquivo de backup...")
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                members = zf.namelist()
                
                # Restaurar banco de dados
                db_members = [m for m in members if m.startswith('data/') and m.endswith('.db')]
                if db_members:
                    if callback:
                        callback("Restaurando banco de dados...")
                    
                    db_member = db_members[0]
                    db_dest = config.DATABASE_PATH
                    
                    # Fazer backup do banco atual antes de sobrescrever
                    if db_dest.exists():
                        backup_atual = db_dest.with_suffix('.db.bak')
                        shutil.copy2(db_dest, backup_atual)
                        logger.info(f"Banco atual salvo em: {backup_atual}")
                    
                    # Extrair novo banco
                    with zf.open(db_member) as source:
                        with open(db_dest, 'wb') as target:
                            target.write(source.read())
                    
                    stats['banco_restaurado'] = True
                    logger.info("Banco de dados restaurado com sucesso")
                
                # Restaurar XMLs
                xml_members = [m for m in members if m.startswith('xmls/') and m.endswith('.xml')]
                if xml_members:
                    if callback:
                        callback(f"Restaurando {len(xml_members)} arquivos XML...")
                    
                    for i, xml_member in enumerate(xml_members):
                        # Calcular caminho de destino
                        rel_path = xml_member[5:]  # Remover 'xmls/' do início
                        dest_path = config.XMLS_DIR / rel_path
                        dest_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        with zf.open(xml_member) as source:
                            with open(dest_path, 'wb') as target:
                                target.write(source.read())
                        
                        stats['xmls_restaurados'] += 1
                        
                        if callback and i % 50 == 0:
                            callback(f"Restaurando XMLs... {i+1}/{len(xml_members)}")
                    
                    logger.info(f"{stats['xmls_restaurados']} XMLs restaurados")
            
            if callback:
                callback("✅ Restauração concluída!")
            
            return stats
            
        except Exception as e:
            logger.error(f"Erro ao restaurar backup: {e}")
            raise
    
    def listar_backups(self) -> List[dict]:
        """
        Lista backups existentes ordenados do mais recente ao mais antigo.
        
        Returns:
            Lista de dicionários com informações dos backups
        """
        backups = []
        
        for zip_file in sorted(self.backups_dir.glob("backup_*.zip"), reverse=True):
            stat = zip_file.stat()
            tamanho_mb = stat.st_size / (1024 * 1024)
            
            # Extrair data do nome do arquivo (backup_YYYYMMDD_HHMMSS.zip)
            try:
                nome_sem_ext = zip_file.stem  # backup_20260223_130000
                data_str = nome_sem_ext.replace("backup_", "")  # 20260223_130000
                data = datetime.strptime(data_str, "%Y%m%d_%H%M%S")
            except (ValueError, IndexError):
                data = datetime.fromtimestamp(stat.st_mtime)
            
            backups.append({
                'nome': zip_file.name,
                'caminho': str(zip_file),
                'data': data,
                'tamanho_mb': round(tamanho_mb, 2),
                'tamanho_bytes': stat.st_size
            })
        
        return backups
