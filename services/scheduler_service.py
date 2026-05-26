"""
Serviço de agendamento automático de downloads e sincronização de status
"""
import logging
import threading
import time
from datetime import date, datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from database import (
    EmpresaRepository, NFSeRepository, SyncLogRepository,
    SchedulerConfigRepository, SyncLog
)
from services.download_service import DownloadService
import config

logger = logging.getLogger(__name__)

# Singleton — uma única instância do scheduler por processo
_scheduler_instance = None
_lock = threading.Lock()


def get_scheduler() -> 'SchedulerService':
    """Retorna a instância singleton do SchedulerService"""
    global _scheduler_instance
    with _lock:
        if _scheduler_instance is None:
            _scheduler_instance = SchedulerService()
        return _scheduler_instance


class SchedulerService:
    """Gerencia agendamento automático de downloads e sincronização de status"""
    
    def __init__(self):
        self.scheduler = BackgroundScheduler(daemon=True)
        self.empresa_repo = EmpresaRepository()
        self.nfse_repo = NFSeRepository()
        self.sync_log_repo = SyncLogRepository()
        self.config_repo = SchedulerConfigRepository()
        self.download_service = DownloadService()
        self._executando = False
    
    def iniciar(self, intervalo_horas: int = None, modo: str = None,
                horario: str = None) -> bool:
        """
        Inicia o agendador.
        
        Args:
            intervalo_horas: Intervalo entre execuções (modo 'intervalo')
            modo: 'intervalo' ou 'horario_fixo'
            horario: Horário no formato 'HH:MM' (modo 'horario_fixo')
        
        Returns:
            True se iniciou com sucesso
        """
        # Carregar configuração salva se não fornecida
        if modo is None:
            modo = self.config_repo.get('modo', 'intervalo')
        if intervalo_horas is None:
            intervalo_horas = int(self.config_repo.get('intervalo_horas', str(config.SCHEDULER_INTERVAL_HOURS)))
        if horario is None:
            horario = self.config_repo.get('horario', '08:00')
        
        try:
            # Salvar configuração
            self.config_repo.set('ativo', 'true')
            self.config_repo.set('modo', modo)
            self.config_repo.set('intervalo_horas', str(intervalo_horas))
            self.config_repo.set('horario', horario)
            
            # Definir trigger conforme o modo
            if modo == 'horario_fixo':
                hora, minuto = horario.split(':')
                trigger = CronTrigger(hour=int(hora), minute=int(minuto))
                desc = f"diariamente às {horario}"
            else:
                trigger = IntervalTrigger(hours=intervalo_horas)
                desc = f"a cada {intervalo_horas} horas"
            
            # Adicionar job
            self.scheduler.add_job(
                self._job_sincronizacao,
                trigger=trigger,
                id='sync_job',
                name='Sincronização automática NFS-e',
                replace_existing=True,
                max_instances=1
            )
            
            if not self.scheduler.running:
                self.scheduler.start()
            logger.info(f"✅ Agendador iniciado/atualizado: execução {desc}")
            return True
            
        except Exception as e:
            logger.error(f"Erro ao iniciar agendador: {e}")
            return False
    
    def parar(self) -> bool:
        """Para o agendador"""
        try:
            if self.scheduler.running:
                self.scheduler.shutdown(wait=False)
                # Recriar scheduler para poder reiniciar depois
                self.scheduler = BackgroundScheduler(daemon=True)
            
            self.config_repo.set('ativo', 'false')
            logger.info("⏹️ Agendador parado")
            return True
            
        except Exception as e:
            logger.error(f"Erro ao parar agendador: {e}")
            return False
    
    def executar_agora(self) -> dict:
        """
        Executa uma sincronização completa imediatamente.
        
        Returns:
            Dicionário com resultados consolidados
        """
        return self._job_sincronizacao()
    
    def get_status(self) -> dict:
        """Retorna status atual do agendador"""
        ativo = self.config_repo.get('ativo', 'false') == 'true'
        modo = self.config_repo.get('modo', 'intervalo')
        intervalo = int(self.config_repo.get('intervalo_horas', str(config.SCHEDULER_INTERVAL_HOURS)))
        horario = self.config_repo.get('horario', '08:00')
        
        proximo_run = None
        if self.scheduler.running:
            job = self.scheduler.get_job('sync_job')
            if job and job.next_run_time:
                proximo_run = job.next_run_time
        
        # Último log
        logs_recentes = self.sync_log_repo.get_recent(limit=1)
        ultimo_run = logs_recentes[0].started_at if logs_recentes else None
        
        return {
            'ativo': ativo and self.scheduler.running,
            'modo': modo,
            'intervalo_horas': intervalo,
            'horario': horario,
            'proximo_run': proximo_run,
            'ultimo_run': ultimo_run,
            'executando': self._executando
        }
    
    def get_historico(self, limit: int = 50):
        """Retorna histórico de execuções"""
        return self.sync_log_repo.get_recent(limit)
    
    def _job_sincronizacao(self) -> dict:
        """
        Job principal: baixa notas de todas as empresas e sincroniza status.
        
        Fluxo:
        1. Lista empresas ativas
        2. Para cada empresa:
           a. Download de notas emitidas e recebidas (tipo AMBAS)
           b. Sincroniza status de notas NORMAL dos últimos 90 dias
        3. Grava SyncLog para cada operação
        """
        if self._executando:
            logger.warning("Sincronização já em andamento, pulando execução")
            return {'erro': 'Já em execução'}
        
        self._executando = True
        resultados = {'empresas': 0, 'notas_novas': 0, 'status_atualizados': 0, 'erros': 0}
        
        try:
            empresas = self.empresa_repo.get_all(apenas_ativas=True)
            
            if not empresas:
                logger.info("Nenhuma empresa ativa para sincronizar")
                self._executando = False
                return resultados
            
            logger.info(f"🔄 Iniciando sincronização automática de {len(empresas)} empresas")
            
            hoje = date.today()
            primeiro_dia_mes = date(hoje.year, hoje.month, 1)
            
            for empresa in empresas:
                resultados['empresas'] += 1
                
                # --- FASE 1: Download de notas ---
                start_download = datetime.now()
                try:
                    logger.info(f"📥 Download: {empresa.razao_social}")
                    
                    stats = self.download_service.download_nfse(
                        empresa=empresa,
                        tipo='AMBAS',
                        data_inicio=primeiro_dia_mes,
                        data_fim=hoje,
                        tipo_periodo='emissao'
                    )
                    
                    resultados['notas_novas'] += stats.get('novas', 0)
                    resultados['erros'] += stats.get('erros', 0)
                    
                    # Gravar log de download
                    self.sync_log_repo.create(SyncLog(
                        empresa_id=empresa.id,
                        empresa_nome=empresa.razao_social,
                        tipo_operacao='DOWNLOAD',
                        notas_encontradas=stats.get('total_encontradas', 0),
                        notas_novas=stats.get('novas', 0),
                        erros=stats.get('erros', 0),
                        detalhes=f"Duplicadas: {stats.get('duplicadas', 0)}",
                        started_at=start_download,
                        finished_at=datetime.now()
                    ))
                    
                except Exception as e:
                    resultados['erros'] += 1
                    logger.error(f"Erro no download de {empresa.razao_social}: {e}")
                    self.sync_log_repo.create(SyncLog(
                        empresa_id=empresa.id,
                        empresa_nome=empresa.razao_social,
                        tipo_operacao='DOWNLOAD',
                        erros=1,
                        detalhes=str(e),
                        started_at=start_download,
                        finished_at=datetime.now()
                    ))
                
                # --- FASE 2: Sincronização de status ---
                start_sync = datetime.now()
                try:
                    # Buscar notas NORMAL dos últimos N dias
                    data_limite = hoje - timedelta(days=config.SYNC_STATUS_DAYS)
                    notas_normais = self.nfse_repo.get_all(
                        empresa_id=empresa.id,
                        status='NORMAL',
                        data_inicio=data_limite,
                        data_fim=hoje
                    )
                    
                    if notas_normais:
                        logger.info(f"🔍 Sincronizando status de {len(notas_normais)} notas de {empresa.razao_social}")
                        
                        sync_stats = self.download_service.sincronizar_status_notas(
                            nfses=notas_normais,
                            empresa=empresa
                        )
                        
                        atualizadas = sync_stats.get('atualizadas', 0)
                        resultados['status_atualizados'] += atualizadas
                        resultados['erros'] += sync_stats.get('erros', 0)
                        
                        # Gravar log de sync
                        self.sync_log_repo.create(SyncLog(
                            empresa_id=empresa.id,
                            empresa_nome=empresa.razao_social,
                            tipo_operacao='SYNC_STATUS',
                            notas_encontradas=len(notas_normais),
                            status_atualizados=atualizadas,
                            erros=sync_stats.get('erros', 0),
                            started_at=start_sync,
                            finished_at=datetime.now()
                        ))
                    else:
                        logger.info(f"Nenhuma nota NORMAL recente para sincronizar em {empresa.razao_social}")
                    
                except Exception as e:
                    resultados['erros'] += 1
                    logger.error(f"Erro na sincronização de status de {empresa.razao_social}: {e}")
                    self.sync_log_repo.create(SyncLog(
                        empresa_id=empresa.id,
                        empresa_nome=empresa.razao_social,
                        tipo_operacao='SYNC_STATUS',
                        erros=1,
                        detalhes=str(e),
                        started_at=start_sync,
                        finished_at=datetime.now()
                    ))
                
                # Pausa entre empresas para evitar sobrecarga da API
                time.sleep(5)
            
            logger.info(f"✅ Sincronização concluída: {resultados}")
            return resultados
            
        except Exception as e:
            logger.error(f"Erro geral na sincronização: {e}")
            resultados['erros'] += 1
            return resultados
            
        finally:
            self._executando = False
    
    def auto_iniciar(self):
        """Verifica configuração salva e inicia automaticamente se necessário"""
        ativo = self.config_repo.get('ativo', 'false')
        if ativo == 'true':
            modo = self.config_repo.get('modo', 'intervalo')
            intervalo = int(self.config_repo.get('intervalo_horas', str(config.SCHEDULER_INTERVAL_HOURS)))
            horario = self.config_repo.get('horario', '08:00')
            logger.info(f"🔄 Auto-iniciando agendador (modo: {modo})")
            self.iniciar(intervalo_horas=intervalo, modo=modo, horario=horario)
