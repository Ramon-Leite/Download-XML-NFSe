"""
Script Avulso de Sincronização e Download de NFS-e (Segundo Plano)
Esse script executa uma varredura completa nas empresas ativas e finaliza imediatamente.
"""
import os
import sys

# Garante que o Python encontre os módulos locais do projeto
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from database import init_database
from services.scheduler_service import get_scheduler

def main():
    print("Iniciando varredura e download silencioso de NFS-e...")
    
    # 1. Configurar logs oficiais da aplicação
    config.setup_logging()
    
    # 2. Inicializar conexão com o banco de dados SQLite
    init_database()
    
    # 3. Chamar a rotina de sincronização singleton
    scheduler = get_scheduler()
    print("Buscando documentos NFS-e para todas as empresas ativas na Receita Federal...")
    
    # Executa a mesma lógica robusta que roda no painel web
    resultados = scheduler.executar_agora()
    
    print(f"Varredura concluída com sucesso! Resultados: {resultados}")

if __name__ == "__main__":
    main()
