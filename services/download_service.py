"""
Serviço para download de NFS-e usando sistema de distribuição por NSU
"""
import logging
import shutil
import time
import traceback
from typing import List, Optional
from datetime import date, datetime
from pathlib import Path
import os
from database import Empresa, NFSe, NFSeRepository, EmpresaRepository, SchedulerConfigRepository
from api import CertificateManager, XMLParser, NFSeClient
import config

logger = logging.getLogger(__name__)


class DownloadService:
    """Serviço para orquestrar download de NFS-e via NSU"""
    
    def __init__(self):
        self.nfse_repository = NFSeRepository()
        self.empresa_repository = EmpresaRepository()
        self.cert_manager = CertificateManager()
        self.xml_parser = XMLParser()
    
    def download_nfse(self, empresa: Empresa, tipo: str, data_inicio: date, data_fim: date,
                     tipo_periodo: str = 'emissao', callback=None) -> dict:
        """
        Faz download de NFS-e de uma empresa usando sistema de NSU
        
        Args:
            empresa: Objeto Empresa
            tipo: 'EMITIDA', 'RECEBIDA' ou 'AMBAS' (usado para filtrar após download)
            data_inicio: Data inicial do período (usado para filtrar após download)
            data_fim: Data final do período (usado para filtrar após download)
            tipo_periodo: 'emissao' ou 'competencia' (usado para filtrar após download)
            callback: Função de callback para progresso (opcional)
        
        Returns:
            Dicionário com estatísticas do download
        """
        stats = {
            'total_encontradas': 0,
            'novas': 0,
            'duplicadas': 0,
            'erros': 0,
            'detalhes_erros': []
        }
        
        try:
            if callback:
                callback("Convertendo certificado...")
            
            # Converter certificado
            cert_path, key_path = self.cert_manager.convert_pfx_to_pem(
                empresa.certificado_path,
                empresa.certificado_senha
            )
            
            # Criar cliente API
            with NFSeClient(cert_path, key_path) as client:
                # Aplicar buffer de contingência no NSU para capturar documentos atrasados
                nsu_com_buffer = max(0, empresa.ultimo_nsu - config.NSU_BUFFER)
                
                if callback:
                    if empresa.ultimo_nsu == 0:
                        callback("🔍 Descobrindo automaticamente onde estão os documentos...")
                    else:
                        callback(f"📥 Buscando documentos desde NSU {nsu_com_buffer} (buffer de {config.NSU_BUFFER})...")
                
                # Buscar documentos desde o NSU com buffer
                # Se nsu_com_buffer for 0, o sistema fará descoberta automática
                documentos = client.buscar_documentos_desde_nsu(
                    nsu_inicial=nsu_com_buffer,
                    cnpj=empresa.cnpj,
                    max_documentos=500
                )
                
                stats['total_encontradas'] = len(documentos)
                
                if len(documentos) == 0:
                    if callback:
                        callback("✅ Conexão com API estabelecida, mas nenhum documento encontrado para este CNPJ.")
                    logger.info("Nenhum documento encontrado - isso é normal se a empresa ainda não emitiu NFS-e no padrão Nacional")
                else:
                    if callback:
                        callback(f"Encontrados {len(documentos)} documentos. Processando...")
                
                # Processar cada documento
                maior_nsu = empresa.ultimo_nsu
                
                for i, doc in enumerate(documentos):
                    if callback and i % 10 == 0:
                        callback(f"Processando documento {i+1}/{len(documentos)}...")
                    
                    try:
                        # Atualizar maior NSU
                        doc_nsu = doc.get('NSU')
                        if doc_nsu and doc_nsu > maior_nsu:
                            maior_nsu = doc_nsu
                        
                        # Processar apenas NFS-e e EVENTO
                        tipo_doc = doc.get('TipoDocumento', '')
                        if tipo_doc.upper() not in ('NFSE', 'EVENTO'):
                            continue
                        
                        # Extrair XML
                        xml_content = client.extrair_xml_documento(doc)
                        if not xml_content:
                            logger.warning(f"Não foi possível extrair XML do documento NSU {doc_nsu}")
                            continue
                        
                        # Parsear XML
                        parsed_data = self.xml_parser.parse_nfse(xml_content)
                        if not parsed_data:
                            logger.warning(f"Erro ao parsear XML do NSU {doc_nsu}")
                            continue
                        
                        # TRATAMENTO DE EVENTO (Cancelamento/Substituição)
                        if parsed_data.get('is_evento'):
                            self._processar_evento(parsed_data, doc_nsu)
                            continue # Evento processado, vai pro próximo NSU.
                        
                        
                        logger.info(f"Dados parseados (NSU {doc_nsu}): Prestador={parsed_data.get('prestador_cnpj')}, Data={parsed_data.get('data_emissao')}")
                        
                        # Verificar se está no período desejado
                        data_emissao = parsed_data.get('data_emissao')
                        data_competencia = parsed_data.get('data_competencia')
                        
                        data_filtro = data_emissao if tipo_periodo == 'emissao' else data_competencia
                        
                        if data_filtro:
                            if data_filtro < data_inicio or data_filtro > data_fim:
                                continue  # Fora do período
                        
                        # Determinar tipo (emitida ou recebida)
                        prestador_cnpj = (parsed_data.get('prestador_cnpj') or '').replace('.', '').replace('/', '').replace('-', '')
                        tomador_cnpj = (parsed_data.get('tomador_cnpj') or '').replace('.', '').replace('/', '').replace('-', '')
                        
                        if prestador_cnpj == empresa.cnpj:
                            tipo_nfse = 'EMITIDA'
                        elif tomador_cnpj == empresa.cnpj:
                            tipo_nfse = 'RECEBIDA'
                        else:
                            continue  # Não é da empresa
                        
                        # Verificar duplicata
                        chave_acesso = parsed_data.get('chave_acesso')
                        if self.nfse_repository.exists_by_chave(chave_acesso):
                            # Conta como duplicada apenas se é do tipo que o usuário pediu
                            if tipo == 'AMBAS' or tipo == tipo_nfse:
                                stats['duplicadas'] += 1
                            continue
                        
                        # Processa e salva a NFS-e
                        self._processar_nfse(parsed_data, empresa, tipo_nfse, xml_content)
                        
                        # Contabilizar apenas as do tipo solicitado pelo usuário
                        if tipo == 'AMBAS' or tipo == tipo_nfse:
                            stats['novas'] += 1
                        
                        logger.info(f"NFS-e salva: {chave_acesso} ({tipo_nfse})")
                    
                    except Exception as e:
                        stats['erros'] += 1
                        stats['detalhes_erros'].append(f"NSU {doc.get('NSU')}: {str(e)}")
                        logger.error(f"Erro ao processar documento: {str(e)}\n{traceback.format_exc()}")
                
                # Atualizar último NSU da empresa
                if maior_nsu > empresa.ultimo_nsu:
                    empresa.ultimo_nsu = maior_nsu
                    self.empresa_repository.update(empresa)
                    logger.info(f"Último NSU atualizado para: {maior_nsu}")
            
            # Limpar arquivos temporários
            self.cert_manager.cleanup_temp_files(empresa.cnpj)
            
            logger.info(f"Download concluído: {stats}")
            return stats
        
        except Exception as e:
            logger.error(f"Erro no download: {str(e)}")
            stats['erros'] += 1
            stats['detalhes_erros'].append(str(e))
            return stats
            
    def sincronizar_status_notas(self, nfses: List[NFSe], empresa: Empresa, callback=None) -> dict:
        """
        Consulta ativamente os eventos de um grupo de notas e atualiza no banco caso cancelada/substituída.
        """
        stats = {'atualizadas': 0, 'erros': 0}
        
        try:
            if callback:
                callback("Preparando certificado para consulta de status...")
                
            # Converter certificado
            cert_path, key_path = self.cert_manager.convert_pfx_to_pem(
                empresa.certificado_path,
                empresa.certificado_senha
            )
            
            with NFSeClient(cert_path, key_path) as client:
                for i, nfse in enumerate(nfses):
                    if callback:
                        callback(f"Consultando status da nota {i+1}/{len(nfses)}...")
                        
                    if nfse.status != 'NORMAL':
                        continue # Já tem status final
                        
                    try:
                        eventos_resp = client.buscar_eventos_nfse(nfse.chave_acesso)
                        if not eventos_resp:
                            time.sleep(1) # delay para não tomar rate limit tão fácil
                            continue
                        
                        # Analisar o JSON de retorno (A API retorna LoteDFe com XMLs compactados)
                        lote_dfe = eventos_resp.get('LoteDFe', [])
                        
                        for doc in lote_dfe:
                            if doc.get('TipoDocumento', '').upper() == 'EVENTO':
                                xml_content = client.extrair_xml_documento(doc)
                                if xml_content:
                                    parsed = self.xml_parser.parse_nfse(xml_content)
                                    if parsed.get('is_evento'):
                                        novo_status = parsed.get('status')
                                        
                                        if novo_status in ('CANCELADA', 'SUBSTITUIDA'):
                                            nfse.status = novo_status
                                            
                                            # Remanejar XML
                                            if nfse.xml_path:
                                                novo_caminho = self._mover_arquivo_xml_status(nfse.xml_path, novo_status)
                                                if novo_caminho:
                                                    nfse.xml_path = novo_caminho
                                                        
                                            self.nfse_repository.update(nfse)
                                            stats['atualizadas'] += 1
                                            break # Achou status e atualizou, pode ir pra próxima nota
                    except Exception as e:
                        stats['erros'] += 1
                        logger.error(f"Erro ao sincronizar chave {nfse.chave_acesso}: {e}")
                    
                    # Respeitar rate limit da API (aumentado para evitar 429 em listas grandes)
                    time.sleep(3)
            
            self.cert_manager.cleanup_temp_files(empresa.cnpj)
            
            return stats
            
        except Exception as e:
            logger.error(f"Erro geral ao sincronizar status: {e}")
            stats['erros'] += 1
            return stats
                
    def _salvar_xml(self, empresa: Empresa, parsed_data: dict, tipo: str, xml_content: str) -> Path:
        """
        Salva XML em arquivo
        
        Args:
            empresa: Empresa
            parsed_data: Dados parseados
            tipo: Tipo da nota
            xml_content: Conteúdo XML
        
        Returns:
            Path do arquivo salvo
        """
        # Determinar diretório: xmls/{cnpj}/{tipo}/{ano}/{mes}/
        data_emissao = parsed_data.get('data_emissao')
        if data_emissao:
            ano = data_emissao.year
            mes = f"{data_emissao.month:02d}"
        else:
            now = datetime.now()
            ano = now.year
            mes = f"{now.month:02d}"
        
        # Buscar caminho customizado das configurações
        try:
            config_repo = SchedulerConfigRepository()
            custom_dir = config_repo.get("xmls_dir")
            if custom_dir and os.path.exists(custom_dir):
                base_xmls_dir = Path(custom_dir)
            else:
                base_xmls_dir = config.XMLS_DIR
        except Exception:
            base_xmls_dir = config.XMLS_DIR
            
        dir_path = base_xmls_dir / empresa.cnpj / tipo.lower() / str(ano) / mes
        dir_path.mkdir(parents=True, exist_ok=True)
        
        # Nome do arquivo: {numero}_{chave}.xml
        numero = parsed_data.get('numero') or 'SEM_NUMERO'
        chave_acesso = parsed_data.get('chave_acesso') or 'SEM_CHAVE'
        chave = chave_acesso[:10]
        filename = f"{numero}_{chave}.xml"
        
        file_path = dir_path / filename
        
        # Salvar
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(xml_content)
        
        return file_path

    def _mover_arquivo_xml_status(self, old_path_str: str, novo_status: str) -> Optional[str]:
        """Move o arquivo XML para a pasta de canceladas ou substituidas"""
        if not old_path_str:
            return None
            
        old_path = Path(old_path_str)
        if not old_path.exists():
            return old_path_str
            
        nova_pasta_tipo = "canceladas" if novo_status == "CANCELADA" else "substituidas"
        
        old_dir = old_path.parent
        mes = old_dir.name
        ano = old_dir.parent.name
        base_cnpj_dir = old_dir.parent.parent.parent
        
        new_dir = base_cnpj_dir / nova_pasta_tipo / str(ano) / mes
        new_dir.mkdir(parents=True, exist_ok=True)
        
        new_path = new_dir / old_path.name
        
        try:
            shutil.move(str(old_path), str(new_path))
            logger.info(f"XML movido para: {new_path}")
            return str(new_path)
        except Exception as e:
            logger.error(f"Erro ao mover arquivo XML {old_path} para {new_path}: {e}")
            return old_path_str
            
    def _processar_evento(self, parsed_data: dict, doc_nsu: int) -> None:
        """Processa um evento de cancelamento ou substituição"""
        chave_acesso = parsed_data.get('chave_acesso')
        novo_status = parsed_data.get('status')
        
        logger.info(f"Evento recebido (NSU {doc_nsu}): Chave={chave_acesso}, Status={novo_status}")
        
        if chave_acesso and novo_status in ('CANCELADA', 'SUBSTITUIDA'):
            # Buscar nota no banco
            nfse_existente = self.nfse_repository.get_by_chave(chave_acesso)
            
            if nfse_existente and nfse_existente.status == 'NORMAL':
                logger.info(f"Atualizando nota {chave_acesso} para {novo_status}")
                
                nfse_existente.status = novo_status
                
                # Remanejar arquivo físico do XML
                if nfse_existente.xml_path:
                    novo_caminho = self._mover_arquivo_xml_status(nfse_existente.xml_path, novo_status)
                    if novo_caminho:
                        nfse_existente.xml_path = novo_caminho
                            
                # Salvar atualização no banco
                self.nfse_repository.update(nfse_existente)

    def _processar_nfse(self, parsed_data: dict, empresa: Empresa, tipo_nfse: str, xml_content: str) -> None:
        """Processa e salva uma nova NFS-e"""
        chave_acesso = parsed_data.get('chave_acesso')
        
        # Salvar XML em arquivo (SEMPRE salva, independente do filtro de tipo)
        xml_path = self._salvar_xml(empresa, parsed_data, tipo_nfse, xml_content)
        
        # Criar objeto NFSe
        nfse = NFSe(
            empresa_id=empresa.id,
            chave_acesso=chave_acesso,
            numero=parsed_data.get('numero'),
            serie=parsed_data.get('serie'),
            numero_dps=parsed_data.get('numero_dps'),
            tipo=tipo_nfse,
            data_emissao=parsed_data.get('data_emissao'),
            data_competencia=parsed_data.get('data_competencia'),
            prestador_cnpj=parsed_data.get('prestador_cnpj'),
            prestador_nome=parsed_data.get('prestador_nome'),
            tomador_cnpj=parsed_data.get('tomador_cnpj'),
            tomador_nome=parsed_data.get('tomador_nome'),
            valor_servicos=parsed_data.get('valor_servicos'),
            valor_iss=parsed_data.get('valor_iss'),
            codigo_servico=parsed_data.get('codigo_servico'),
            descricao_servico=parsed_data.get('descricao_servico'),
            status=parsed_data.get('status', 'NORMAL'),
            xml_path=str(xml_path)
        )
        
        # Salvar no banco (SEMPRE salva para não pular NSU)
        self.nfse_repository.create(nfse)


class DuplicateNFSeError(Exception):
    """Exceção para NFS-e duplicada"""
    pass
