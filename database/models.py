"""
Modelos de dados para o sistema NFS-e Nacional
"""
from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional
from decimal import Decimal

@dataclass
class Empresa:
    """Modelo de dados para empresa"""
    id: Optional[int] = None
    cnpj: str = ""
    razao_social: str = ""
    nome_fantasia: Optional[str] = None
    certificado_path: str = ""
    certificado_senha: str = ""
    ultimo_nsu: int = 0
    ativo: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def __post_init__(self):
        """Validações básicas"""
        if self.cnpj:
            # Remove formatação do CNPJ
            self.cnpj = ''.join(filter(str.isdigit, self.cnpj))
    
    @property
    def cnpj_formatado(self) -> str:
        """Retorna CNPJ formatado XX.XXX.XXX/XXXX-XX"""
        if len(self.cnpj) == 14:
            return f"{self.cnpj[:2]}.{self.cnpj[2:5]}.{self.cnpj[5:8]}/{self.cnpj[8:12]}-{self.cnpj[12:]}"
        return self.cnpj
    
    def to_dict(self) -> dict:
        """Converte para dicionário"""
        return {
            'id': self.id,
            'cnpj': self.cnpj,
            'razao_social': self.razao_social,
            'nome_fantasia': self.nome_fantasia,
            'certificado_path': self.certificado_path,
            'certificado_senha': self.certificado_senha,
            'ultimo_nsu': self.ultimo_nsu,
            'ativo': self.ativo,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


@dataclass
class NFSe:
    """Modelo de dados para NFS-e"""
    id: Optional[int] = None
    empresa_id: int = 0
    chave_acesso: str = ""
    numero: Optional[str] = None
    serie: Optional[str] = None
    numero_dps: Optional[str] = None
    tipo: str = "EMITIDA"  # EMITIDA ou RECEBIDA
    data_emissao: Optional[date] = None
    data_competencia: Optional[date] = None
    prestador_cnpj: Optional[str] = None
    prestador_nome: Optional[str] = None
    tomador_cnpj: Optional[str] = None
    tomador_nome: Optional[str] = None
    valor_servicos: Optional[Decimal] = None
    valor_iss: Optional[Decimal] = None
    # Impostos retidos (ver api/retencoes.py). iss_retido guarda o vISSQN só quando
    # a flag tpRetISSQN indica retenção; valor_retencoes é a soma de todos.
    iss_retido: Optional[Decimal] = None
    ret_pis: Optional[Decimal] = None
    ret_cofins: Optional[Decimal] = None
    ret_irrf: Optional[Decimal] = None
    ret_csll: Optional[Decimal] = None
    ret_inss: Optional[Decimal] = None
    valor_retencoes: Optional[Decimal] = None
    codigo_servico: Optional[str] = None
    codigo_tributacao_nacional: Optional[str] = None
    codigo_tributacao_municipal: Optional[str] = None
    descricao_servico: Optional[str] = None
    status: str = "NORMAL"  # NORMAL, CANCELADA, SUBSTITUIDA
    xml_path: Optional[str] = None
    downloaded_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    
    def __post_init__(self):
        """Validações e formatações"""
        # Remove formatação de CNPJs
        if self.prestador_cnpj:
            self.prestador_cnpj = ''.join(filter(str.isdigit, self.prestador_cnpj))
        if self.tomador_cnpj:
            self.tomador_cnpj = ''.join(filter(str.isdigit, self.tomador_cnpj))
    
    @staticmethod
    def formatar_cnpj(cnpj: str) -> str:
        """Formata CNPJ para XX.XXX.XXX/XXXX-XX"""
        if not cnpj:
            return ""
        cnpj_limpo = ''.join(filter(str.isdigit, cnpj))
        if len(cnpj_limpo) == 14:
            return f"{cnpj_limpo[:2]}.{cnpj_limpo[2:5]}.{cnpj_limpo[5:8]}/{cnpj_limpo[8:12]}-{cnpj_limpo[12:]}"
        return cnpj
    
    @property
    def prestador_cnpj_formatado(self) -> str:
        """Retorna CNPJ do prestador formatado"""
        return self.formatar_cnpj(self.prestador_cnpj)
    
    @property
    def tomador_cnpj_formatado(self) -> str:
        """Retorna CNPJ do tomador formatado"""
        return self.formatar_cnpj(self.tomador_cnpj)
    
    def to_dict(self) -> dict:
        """Converte para dicionário"""
        return {
            'id': self.id,
            'empresa_id': self.empresa_id,
            'chave_acesso': self.chave_acesso,
            'numero': self.numero,
            'serie': self.serie,
            'numero_dps': self.numero_dps,
            'tipo': self.tipo,
            'data_emissao': self.data_emissao.isoformat() if self.data_emissao else None,
            'data_competencia': self.data_competencia.isoformat() if self.data_competencia else None,
            'prestador_cnpj': self.prestador_cnpj,
            'prestador_nome': self.prestador_nome,
            'tomador_cnpj': self.tomador_cnpj,
            'tomador_nome': self.tomador_nome,
            'valor_servicos': float(self.valor_servicos) if self.valor_servicos else None,
            'valor_iss': float(self.valor_iss) if self.valor_iss else None,
            'iss_retido': float(self.iss_retido or 0),
            'ret_pis': float(self.ret_pis or 0),
            'ret_cofins': float(self.ret_cofins or 0),
            'ret_irrf': float(self.ret_irrf or 0),
            'ret_csll': float(self.ret_csll or 0),
            'ret_inss': float(self.ret_inss or 0),
            'valor_retencoes': float(self.valor_retencoes or 0),
            'codigo_servico': self.codigo_servico,
            'codigo_tributacao_nacional': self.codigo_tributacao_nacional,
            'codigo_tributacao_municipal': self.codigo_tributacao_municipal,
            'descricao_servico': self.descricao_servico,
            'status': self.status,
            'xml_path': self.xml_path,
            'downloaded_at': self.downloaded_at,
            'created_at': self.created_at
        }


@dataclass
class SyncLog:
    """Modelo de dados para log de sincronização automática"""
    id: Optional[int] = None
    empresa_id: int = 0
    empresa_nome: str = ""
    tipo_operacao: str = "DOWNLOAD"  # DOWNLOAD ou SYNC_STATUS
    notas_encontradas: int = 0
    notas_novas: int = 0
    status_atualizados: int = 0
    erros: int = 0
    detalhes: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

