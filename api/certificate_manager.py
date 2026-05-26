"""
Gerenciador de certificados digitais A1 para autenticação mTLS
"""
import os
import atexit
import logging
import tempfile
from pathlib import Path
from typing import Tuple, Optional
from datetime import datetime, timezone
from cryptography.hazmat.primitives.serialization import pkcs12, Encoding, PrivateFormat, NoEncryption
from cryptography import x509
from cryptography.hazmat.backends import default_backend
import config

logger = logging.getLogger(__name__)


class CertificateManager:
    """Gerencia conversão e validação de certificados digitais A1"""
    
    def __init__(self):
        self.temp_dir = Path(tempfile.gettempdir()) / "nfse_certs"
        self.temp_dir.mkdir(exist_ok=True)
        # Registrar limpeza automática ao encerrar o programa
        atexit.register(self._cleanup_all_temp_files)
    
    def convert_pfx_to_pem(self, pfx_path: str, password: str) -> Tuple[str, str]:
        """
        Converte certificado .pfx para arquivos .pem (certificado e chave privada)
        
        Args:
            pfx_path: Caminho do arquivo .pfx
            password: Senha do certificado
        
        Returns:
            Tuple com (caminho_certificado.pem, caminho_chave.pem)
        """
        # Ler arquivo .pfx
        with open(pfx_path, 'rb') as f:
            pfx_data = f.read()
        
        # Carregar PKCS12
        try:
            private_key, certificate, additional_certs = pkcs12.load_key_and_certificates(
                pfx_data,
                password.encode() if password else None,
                backend=default_backend()
            )
        except Exception as e:
            raise ValueError(f"Erro ao carregar certificado. Verifique a senha: {str(e)}")
        
        if not certificate or not private_key:
            raise ValueError("Certificado ou chave privada não encontrados no arquivo .pfx")
        
        # Gerar nomes de arquivo baseados no CNPJ do certificado
        cnpj = self.extract_cnpj_from_certificate(certificate)
        cert_filename = f"cert_{cnpj}.pem"
        key_filename = f"key_{cnpj}.pem"
        
        cert_path = self.temp_dir / cert_filename
        key_path = self.temp_dir / key_filename
        
        # Salvar certificado em formato PEM
        with open(cert_path, 'wb') as f:
            f.write(certificate.public_bytes(Encoding.PEM))
        
        # Salvar chave privada em formato PEM
        with open(key_path, 'wb') as f:
            f.write(private_key.private_bytes(
                encoding=Encoding.PEM,
                format=PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=NoEncryption()
            ))
        
        return str(cert_path), str(key_path)
    
    def extract_cnpj_from_certificate(self, certificate) -> str:
        """
        Extrai CNPJ do certificado digital
        
        Args:
            certificate: Objeto certificado x509
        
        Returns:
            CNPJ extraído do certificado
        """
        # Tentar extrair do CN (Common Name)
        subject = certificate.subject
        
        # Procurar pelo CN
        cn_attributes = subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
        if cn_attributes:
            cn = cn_attributes[0].value
            if ':' in cn:
                parts = cn.split(':')
                for i, part in enumerate(parts):
                    if part.upper() == 'CNPJ' and i + 1 < len(parts):
                        return parts[i + 1][:14]  # Pegar apenas os 14 dígitos
        
        # Tentar extrair do serialNumber
        serial_attributes = subject.get_attributes_for_oid(x509.oid.NameOID.SERIAL_NUMBER)
        if serial_attributes:
            serial = serial_attributes[0].value
            # Remover caracteres não numéricos
            cnpj = ''.join(filter(str.isdigit, serial))
            if len(cnpj) >= 14:
                return cnpj[:14]
        
        # Fallback: usar timestamp
        return datetime.now().strftime("%Y%m%d%H%M%S")
    
    def validate_certificate(self, pfx_path: str, password: str) -> dict:
        """
        Valida certificado e retorna informações
        
        Args:
            pfx_path: Caminho do arquivo .pfx
            password: Senha do certificado
        
        Returns:
            Dicionário com informações do certificado
        """
        try:
            # Ler arquivo .pfx
            with open(pfx_path, 'rb') as f:
                pfx_data = f.read()
            
            # Carregar PKCS12
            private_key, certificate, additional_certs = pkcs12.load_key_and_certificates(
                pfx_data,
                password.encode() if password else None,
                backend=default_backend()
            )
            
            if not certificate:
                return {'valid': False, 'error': 'Certificado não encontrado no arquivo'}
            
            # Extrair informações
            subject = certificate.subject
            
            # Data de validade
            expiry_date = certificate.not_valid_after_utc.replace(tzinfo=None)
            
            # Verificar se está válido
            is_valid = expiry_date > datetime.now(timezone.utc).replace(tzinfo=None)
            
            # Extrair CNPJ
            cnpj = self.extract_cnpj_from_certificate(certificate)
            
            # Extrair CN
            cn_attributes = subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
            subject_cn = cn_attributes[0].value if cn_attributes else 'N/A'
            
            # Extrair issuer
            issuer = certificate.issuer
            issuer_cn_attributes = issuer.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
            issuer_cn = issuer_cn_attributes[0].value if issuer_cn_attributes else 'N/A'
            
            return {
                'valid': True,
                'is_expired': not is_valid,
                'expiry_date': expiry_date,
                'cnpj': cnpj,
                'subject_cn': subject_cn,
                'issuer': issuer_cn,
                'serial_number': certificate.serial_number
            }
        
        except Exception as e:
            return {
                'valid': False,
                'error': str(e)
            }
    
    def cleanup_temp_files(self, cnpj: str):
        """Remove arquivos temporários de certificado"""
        cert_path = self.temp_dir / f"cert_{cnpj}.pem"
        key_path = self.temp_dir / f"key_{cnpj}.pem"
        
        for path in (cert_path, key_path):
            try:
                if path.exists():
                    path.unlink()
            except Exception as e:
                logger.warning(f"Não foi possível remover arquivo temporário {path}: {e}")
    
    def _cleanup_all_temp_files(self):
        """Remove todos os arquivos temporários de certificado (chamado via atexit)"""
        try:
            if self.temp_dir.exists():
                for pem_file in self.temp_dir.glob("*.pem"):
                    try:
                        pem_file.unlink()
                    except Exception as e:
                        logger.warning(f"Falha ao limpar {pem_file}: {e}")
        except Exception as e:
            logger.warning(f"Falha na limpeza de arquivos temporários: {e}")
