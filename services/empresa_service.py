"""
Serviço para gerenciamento de empresas
"""
import logging
import shutil
from typing import List, Optional
from pathlib import Path
from database import Empresa, EmpresaRepository
from api import CertificateManager
import config

logger = logging.getLogger(__name__)


class EmpresaService:
    """Serviço para operações com empresas"""
    
    def __init__(self):
        self.repository = EmpresaRepository()
        self.cert_manager = CertificateManager()
    
    def cadastrar_empresa(self, cnpj: str, razao_social: str, nome_fantasia: Optional[str],
                         certificado_path: str, certificado_senha: str) -> dict:
        """
        Cadastra uma nova empresa
        
        Args:
            cnpj: CNPJ da empresa
            razao_social: Razão social
            nome_fantasia: Nome fantasia (opcional)
            certificado_path: Caminho do arquivo .pfx
            certificado_senha: Senha do certificado
        
        Returns:
            Dicionário com resultado da operação
        """
        try:
            # Validar certificado
            cert_info = self.cert_manager.validate_certificate(certificado_path, certificado_senha)
            
            if not cert_info.get('valid'):
                return {
                    'success': False,
                    'error': f"Certificado inválido: {cert_info.get('error', 'Erro desconhecido')}"
                }
            
            if cert_info.get('is_expired'):
                return {
                    'success': False,
                    'error': f"Certificado expirado em {cert_info['expiry_date'].strftime('%d/%m/%Y')}"
                }
            
            # Verificar se empresa já existe
            cnpj_limpo = ''.join(filter(str.isdigit, cnpj))
            empresa_existente = self.repository.get_by_cnpj(cnpj_limpo)
            
            if empresa_existente:
                return {
                    'success': False,
                    'error': 'Empresa já cadastrada'
                }
            
            # Copiar certificado para diretório seguro
            cert_dest = config.CERTIFICADOS_DIR / f"{cnpj_limpo}.pfx"
            shutil.copy2(certificado_path, cert_dest)
            
            # Criar empresa
            empresa = Empresa(
                cnpj=cnpj_limpo,
                razao_social=razao_social,
                nome_fantasia=nome_fantasia,
                certificado_path=str(cert_dest),
                certificado_senha=certificado_senha,
                ativo=True
            )
            
            empresa_id = self.repository.create(empresa)
            
            logger.info(f"Empresa cadastrada: {razao_social} (ID: {empresa_id})")
            
            return {
                'success': True,
                'empresa_id': empresa_id,
                'cert_info': cert_info
            }
        
        except Exception as e:
            logger.error(f"Erro ao cadastrar empresa: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def listar_empresas(self, apenas_ativas: bool = True) -> List[Empresa]:
        """Lista todas as empresas"""
        return self.repository.get_all(apenas_ativas)
    
    def obter_empresa(self, empresa_id: int) -> Optional[Empresa]:
        """Obtém empresa por ID"""
        return self.repository.get_by_id(empresa_id)
    
    def atualizar_empresa(self, empresa: Empresa) -> bool:
        """Atualiza dados de uma empresa"""
        return self.repository.update(empresa)
    
    def excluir_empresa(self, empresa_id: int) -> bool:
        """Exclui uma empresa"""
        # Remover certificado
        empresa = self.repository.get_by_id(empresa_id)
        if empresa and empresa.certificado_path:
            cert_path = Path(empresa.certificado_path)
            if cert_path.exists():
                cert_path.unlink()
        
        return self.repository.delete(empresa_id)
    
    def validar_certificado_empresa(self, empresa_id: int) -> dict:
        """Valida o certificado de uma empresa"""
        empresa = self.repository.get_by_id(empresa_id)
        
        if not empresa:
            return {'valid': False, 'error': 'Empresa não encontrada'}
        
        return self.cert_manager.validate_certificate(
            empresa.certificado_path,
            empresa.certificado_senha
        )
