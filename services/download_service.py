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
from database import (
    Empresa, NFSe, NFSeRepository, EmpresaRepository,
    SchedulerConfigRepository, EventoPendenteRepository
)
from api import CertificateManager, XMLParser, NFSeClient
import config

logger = logging.getLogger(__name__)


class DownloadService:
    """Serviço para orquestrar download de NFS-e via NSU"""

    def __init__(self):
        self.nfse_repository = NFSeRepository()
        self.empresa_repository = EmpresaRepository()
        self.evento_pendente_repository = EventoPendenteRepository()
        self.cert_manager = CertificateManager()
        self.xml_parser = XMLParser()

    def download_nfse(self, empresa: Empresa, tipo: str, data_inicio: date, data_fim: date,
                     tipo_periodo: str = 'emissao', callback=None) -> dict:
        """
        Sincroniza TODOS os documentos disponíveis na distribuição da empresa.

        IMPORTANTE: o download é uma SINCRONIZAÇÃO — toda nota recebida é
        salva, independentemente de tipo/período. Os parâmetros tipo,
        data_inicio, data_fim e tipo_periodo servem apenas para informar
        nas estatísticas quantas notas novas caíram fora do período pedido.
        (Antes, notas fora do filtro eram descartadas com o ponteiro NSU
        avançando — a causa das "notas sumidas".)

        O ponteiro ultimo_nsu só avança até o último documento processado
        com sucesso: uma falha transitória segura o ponteiro e o documento
        é reprocessado na próxima execução.

        Returns:
            Dicionário com estatísticas do download
        """
        stats = {
            'total_encontradas': 0,
            'novas': 0,
            'novas_fora_periodo': 0,
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
                # Buffer de contingência: refaz os últimos N NSUs (deduplicados adiante)
                nsu_inicio = max(0, empresa.ultimo_nsu - config.NSU_BUFFER)

                if callback:
                    if empresa.ultimo_nsu == 0:
                        callback("📥 Buscando todos os documentos da distribuição (NSU 0)...")
                    else:
                        callback(f"📥 Buscando documentos desde NSU {nsu_inicio} (buffer de {config.NSU_BUFFER})...")

                ponteiro = empresa.ultimo_nsu
                falha_ocorreu = False
                docs_processados = 0

                for lote in client.iterar_lotes_dfe(nsu_inicio):
                    stats['total_encontradas'] += len(lote)

                    for doc in lote:
                        doc_nsu = doc.get('NSU') or 0

                        ok = self._processar_documento(
                            client, doc, empresa, tipo, data_inicio, data_fim, tipo_periodo, stats
                        )

                        if not ok:
                            # Segura o ponteiro: este documento (e os seguintes)
                            # serão re-baixados na próxima execução
                            falha_ocorreu = True
                        elif not falha_ocorreu and doc_nsu > ponteiro:
                            ponteiro = doc_nsu

                        docs_processados += 1
                        if callback and docs_processados % 10 == 0:
                            callback(f"Processando... {docs_processados} documentos ({stats['novas']} novas)")

                    # Persistir progresso a cada lote (crash no meio não perde o avanço)
                    if ponteiro > empresa.ultimo_nsu:
                        empresa.ultimo_nsu = ponteiro
                        self.empresa_repository.update(empresa)

                if stats['total_encontradas'] == 0:
                    if callback:
                        callback("✅ Conexão com API estabelecida, mas nenhum documento novo para este CNPJ.")
                    logger.info("Nenhum documento novo - normal se a empresa ainda não emitiu NFS-e no padrão Nacional")

                if falha_ocorreu:
                    logger.warning(
                        f"Falhas transitórias durante o download: ponteiro NSU mantido em {empresa.ultimo_nsu}; "
                        "os documentos com falha serão reprocessados na próxima execução"
                    )

            logger.info(f"Download concluído: {stats}")
            return stats

        except Exception as e:
            logger.error(f"Erro no download: {str(e)}")
            stats['erros'] += 1
            stats['detalhes_erros'].append(str(e))
            return stats

        finally:
            # Sempre remover os PEMs temporários (contêm a chave privada)
            try:
                self.cert_manager.cleanup_temp_files(empresa.cnpj)
            except Exception as e:
                logger.warning(f"Falha ao limpar arquivos temporários de certificado: {e}")

    def _processar_documento(self, client: NFSeClient, doc: dict, empresa: Empresa,
                             tipo: str, data_inicio: date, data_fim: date,
                             tipo_periodo: str, stats: dict) -> bool:
        """
        Processa um documento da distribuição.

        Returns:
            True  — documento tratado (salvo, duplicado, irrelevante ou
                    preservado em quarentena): o ponteiro NSU pode avançar.
            False — falha possivelmente transitória (banco/disco): o ponteiro
                    NSU é segurado para reprocessar na próxima execução.
        """
        doc_nsu = doc.get('NSU')

        try:
            # Processar apenas NFS-e e EVENTO
            tipo_doc = (doc.get('TipoDocumento') or '').upper()
            if tipo_doc not in ('NFSE', 'EVENTO'):
                return True

            # Extrair XML
            xml_content = client.extrair_xml_documento(doc)
            if not xml_content:
                # Conteúdo ilegível (base64/gzip): preservar o bruto e seguir
                stats['erros'] += 1
                stats['detalhes_erros'].append(f"NSU {doc_nsu}: XML não pôde ser extraído (bruto em quarentena)")
                self._salvar_quarentena(empresa, doc.get('ArquivoXml') or '', doc_nsu, 'extracao', extensao='b64')
                return True

            # Parsear XML
            parsed_data = self.xml_parser.parse_nfse(xml_content)
            if not parsed_data:
                # XML não reconhecido: preservar em quarentena e seguir
                stats['erros'] += 1
                stats['detalhes_erros'].append(f"NSU {doc_nsu}: erro de parse (XML em quarentena)")
                self._salvar_quarentena(empresa, xml_content, doc_nsu, 'parse')
                return True

            # TRATAMENTO DE EVENTO (Cancelamento/Substituição)
            if parsed_data.get('is_evento'):
                self._processar_evento(parsed_data, doc_nsu)
                return True

            # Determinar tipo (emitida ou recebida)
            prestador_cnpj = (parsed_data.get('prestador_cnpj') or '').replace('.', '').replace('/', '').replace('-', '')
            tomador_cnpj = (parsed_data.get('tomador_cnpj') or '').replace('.', '').replace('/', '').replace('-', '')

            if prestador_cnpj == empresa.cnpj:
                tipo_nfse = 'EMITIDA'
            elif tomador_cnpj == empresa.cnpj:
                tipo_nfse = 'RECEBIDA'
            else:
                # A distribuição entrega notas em que a empresa é parte
                # (ex.: intermediária) ou o layout não permitiu extrair o CNPJ.
                # Preservar em quarentena para não perder o documento.
                logger.warning(
                    f"NSU {doc_nsu}: empresa {empresa.cnpj} não é prestador nem tomador "
                    f"(prestador={prestador_cnpj or '?'}, tomador={tomador_cnpj or '?'}) — XML em quarentena"
                )
                self._salvar_quarentena(empresa, xml_content, doc_nsu, 'sem_vinculo')
                return True

            chave_acesso = parsed_data.get('chave_acesso')
            if not chave_acesso:
                stats['erros'] += 1
                stats['detalhes_erros'].append(f"NSU {doc_nsu}: nota sem chave de acesso (XML em quarentena)")
                self._salvar_quarentena(empresa, xml_content, doc_nsu, 'sem_chave')
                return True

            # Verificar duplicata (por empresa: a mesma nota pode existir
            # para a prestadora e para a tomadora, se ambas cadastradas)
            if self.nfse_repository.exists_by_chave(chave_acesso, empresa_id=empresa.id):
                stats['duplicadas'] += 1
                return True

            # Salvar SEMPRE, independente de tipo/período solicitados
            self._processar_nfse(parsed_data, empresa, tipo_nfse, xml_content)
            stats['novas'] += 1

            # Estatística informativa: nota fora do período pedido pelo usuário
            data_filtro = parsed_data.get('data_emissao') if tipo_periodo == 'emissao' \
                else parsed_data.get('data_competencia')
            if data_filtro and (data_filtro < data_inicio or data_filtro > data_fim):
                stats['novas_fora_periodo'] += 1

            logger.info(f"NFS-e salva: {chave_acesso} ({tipo_nfse})")
            return True

        except Exception as e:
            # Falha possivelmente transitória (banco travado, disco cheio...):
            # segurar o ponteiro para reprocessar este NSU na próxima execução
            stats['erros'] += 1
            stats['detalhes_erros'].append(f"NSU {doc_nsu}: {str(e)}")
            logger.error(f"Erro ao processar documento NSU {doc_nsu}: {str(e)}\n{traceback.format_exc()}")
            return False
            
    @staticmethod
    def montar_id_dps(cmun: str, cnpj: str, serie: str, numero_dps: int) -> str:
        """
        Monta o id derivável da DPS:
        DPS + cMun(7) + tpInsc(1: 2=CNPJ) + inscrição(14) + série(5) + nDPS(15)
        """
        serie_digitos = ''.join(c for c in str(serie) if c.isdigit()) or '0'
        return f"DPS{cmun}2{cnpj.zfill(14)}{serie_digitos.zfill(5)}{int(numero_dps):015d}"

    def buscar_notas_faltantes(self, empresa: Empresa, callback=None, max_consultas: int = 50) -> dict:
        """
        Busca ativa de notas faltantes: para cada lacuna na numeração de DPS
        das notas emitidas, consulta a SEFIN Nacional (GET /dps/{id} → chave
        de acesso → GET /nfse/{chave} → XML) e salva a nota recuperada.

        Lacunas legítimas (DPS que nunca virou NFS-e) são contabilizadas em
        'sem_nfse' e não são erro.

        Args:
            empresa: Empresa cujas lacunas serão verificadas
            max_consultas: Máximo de DPS consultadas por execução

        Returns:
            Estatísticas da recuperação
        """
        stats = {
            'faltantes_detectadas': 0,
            'consultadas': 0,
            'recuperadas': 0,
            'sem_nfse': 0,
            'erros': 0,
            'detalhes': []
        }

        gaps = self.nfse_repository.detectar_gaps_dps(empresa.id)
        stats['faltantes_detectadas'] = sum(len(g['faltantes']) for g in gaps)

        if not gaps:
            if callback:
                callback("✅ Nenhuma lacuna de numeração DPS detectada.")
            return stats

        try:
            if callback:
                callback("Convertendo certificado...")

            cert_path, key_path = self.cert_manager.convert_pfx_to_pem(
                empresa.certificado_path,
                empresa.certificado_senha
            )

            with NFSeClient(cert_path, key_path) as client:
                for gap in gaps:
                    faltantes = gap['faltantes']

                    # Proteção contra falso gap gigante (ex.: reinício de numeração)
                    if len(faltantes) > 1000:
                        stats['detalhes'].append(
                            f"Série {gap['serie']}: {len(faltantes)} lacunas — provável salto de "
                            "numeração, série ignorada"
                        )
                        logger.warning(f"Série {gap['serie']} com {len(faltantes)} lacunas — ignorada")
                        continue

                    for ndps in faltantes:
                        if stats['consultadas'] >= max_consultas:
                            stats['detalhes'].append(
                                f"Limite de {max_consultas} consultas atingido — execute novamente "
                                "para continuar"
                            )
                            return stats

                        if callback:
                            callback(f"Consultando DPS {ndps} (série {gap['serie']})...")

                        id_dps = self.montar_id_dps(gap['cmun'], empresa.cnpj, gap['serie'], ndps)
                        chave = client.consultar_chave_por_dps(id_dps)
                        stats['consultadas'] += 1

                        if not chave:
                            # DPS nunca virou NFS-e: lacuna legítima
                            stats['sem_nfse'] += 1
                            time.sleep(0.4)
                            continue

                        if self.nfse_repository.exists_by_chave(chave, empresa_id=empresa.id):
                            stats['detalhes'].append(f"DPS {ndps}: nota {chave} já estava no banco")
                            time.sleep(0.4)
                            continue

                        xml_content = client.consultar_nfse_por_chave(chave)
                        if not xml_content:
                            stats['erros'] += 1
                            stats['detalhes'].append(f"DPS {ndps}: chave {chave} localizada, mas XML indisponível")
                            time.sleep(0.4)
                            continue

                        parsed_data = self.xml_parser.parse_nfse(xml_content)
                        if not parsed_data or parsed_data.get('is_evento'):
                            stats['erros'] += 1
                            stats['detalhes'].append(f"DPS {ndps}: XML recuperado não pôde ser processado (em quarentena)")
                            self._salvar_quarentena(empresa, xml_content, f"dps_{ndps}", 'recuperacao')
                            time.sleep(0.4)
                            continue

                        prestador_cnpj = (parsed_data.get('prestador_cnpj') or '').replace('.', '').replace('/', '').replace('-', '')
                        if prestador_cnpj != empresa.cnpj:
                            stats['erros'] += 1
                            stats['detalhes'].append(f"DPS {ndps}: prestador do XML não confere (em quarentena)")
                            self._salvar_quarentena(empresa, xml_content, f"dps_{ndps}", 'prestador_divergente')
                            time.sleep(0.4)
                            continue

                        self._processar_nfse(parsed_data, empresa, 'EMITIDA', xml_content)
                        stats['recuperadas'] += 1
                        stats['detalhes'].append(
                            f"✅ Nota nº {parsed_data.get('numero')} (DPS {ndps}) recuperada"
                        )
                        logger.info(f"Nota faltante recuperada via DPS {ndps}: {chave}")

                        if callback:
                            callback(f"✅ Recuperada nota nº {parsed_data.get('numero')} (DPS {ndps})")

                        time.sleep(0.4)

            return stats

        except Exception as e:
            logger.error(f"Erro na busca de notas faltantes: {str(e)}\n{traceback.format_exc()}")
            stats['erros'] += 1
            stats['detalhes'].append(str(e))
            return stats

        finally:
            try:
                self.cert_manager.cleanup_temp_files(empresa.cnpj)
            except Exception as e:
                logger.warning(f"Falha ao limpar arquivos temporários de certificado: {e}")

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
                    
                    # Pausa preventiva entre consultas; o cliente já faz
                    # backoff exponencial automático se levar 429
                    time.sleep(1)

            return stats

        except Exception as e:
            logger.error(f"Erro geral ao sincronizar status: {e}")
            stats['erros'] += 1
            return stats

        finally:
            # Sempre remover os PEMs temporários (contêm a chave privada)
            try:
                self.cert_manager.cleanup_temp_files(empresa.cnpj)
            except Exception as e:
                logger.warning(f"Falha ao limpar arquivos temporários de certificado: {e}")
                
    def _base_xmls_dir(self) -> Path:
        """Diretório base dos XMLs (customizável nas configurações)"""
        try:
            config_repo = SchedulerConfigRepository()
            custom_dir = config_repo.get("xmls_dir")
            if custom_dir and os.path.exists(custom_dir):
                return Path(custom_dir)
        except Exception:
            pass
        return config.XMLS_DIR

    def _salvar_quarentena(self, empresa: Empresa, conteudo: str, doc_nsu, motivo: str,
                           extensao: str = 'xml') -> None:
        """
        Preserva em disco um documento que não pôde ser processado
        (parse falhou, sem vínculo com a empresa etc.), para que nada
        recebido da distribuição seja perdido.
        """
        if not conteudo:
            return
        try:
            dir_path = self._base_xmls_dir() / empresa.cnpj / 'quarentena'
            dir_path.mkdir(parents=True, exist_ok=True)
            file_path = dir_path / f"nsu_{doc_nsu}_{motivo}.{extensao}"
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(conteudo)
            logger.info(f"Documento NSU {doc_nsu} preservado em quarentena: {file_path}")
        except Exception as e:
            logger.error(f"Erro ao salvar quarentena do NSU {doc_nsu}: {e}")

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

        dir_path = self._base_xmls_dir() / empresa.cnpj / tipo.lower() / str(ano) / mes
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
            
    def _processar_evento(self, parsed_data: dict, doc_nsu) -> None:
        """
        Processa um evento de cancelamento ou substituição.

        Atualiza TODAS as notas com a chave (a mesma nota pode existir para
        mais de uma empresa cadastrada). Se a nota ainda não foi baixada,
        o evento fica pendente e é aplicado quando a nota chegar.
        """
        chave_acesso = parsed_data.get('chave_acesso')
        novo_status = parsed_data.get('status')

        logger.info(f"Evento recebido (NSU {doc_nsu}): Chave={chave_acesso}, Status={novo_status}")

        if not chave_acesso or novo_status not in ('CANCELADA', 'SUBSTITUIDA'):
            return

        notas = self.nfse_repository.get_all_by_chave(chave_acesso)

        if not notas:
            # Evento chegou antes da nota: guardar para aplicar depois
            logger.info(f"Nota {chave_acesso} ainda não existe — evento {novo_status} ficará pendente")
            self.evento_pendente_repository.add(chave_acesso, novo_status)
            return

        for nfse_existente in notas:
            if nfse_existente.status != 'NORMAL':
                continue

            logger.info(f"Atualizando nota {chave_acesso} (empresa {nfse_existente.empresa_id}) para {novo_status}")
            nfse_existente.status = novo_status

            # Remanejar arquivo físico do XML
            if nfse_existente.xml_path:
                novo_caminho = self._mover_arquivo_xml_status(nfse_existente.xml_path, novo_status)
                if novo_caminho:
                    nfse_existente.xml_path = novo_caminho

            self.nfse_repository.update(nfse_existente)

    def _processar_nfse(self, parsed_data: dict, empresa: Empresa, tipo_nfse: str, xml_content: str) -> None:
        """Processa e salva uma nova NFS-e"""
        chave_acesso = parsed_data.get('chave_acesso')

        # data_emissao é NOT NULL no banco: usar competência como fallback
        # para não perder a nota por causa de um layout de data inesperado
        if not parsed_data.get('data_emissao'):
            fallback = parsed_data.get('data_competencia') or datetime.now().date()
            logger.warning(f"Nota {chave_acesso} sem data de emissão parseável — usando {fallback}")
            parsed_data['data_emissao'] = fallback

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
            iss_retido=parsed_data.get('iss_retido'),
            ret_pis=parsed_data.get('ret_pis'),
            ret_cofins=parsed_data.get('ret_cofins'),
            ret_irrf=parsed_data.get('ret_irrf'),
            ret_csll=parsed_data.get('ret_csll'),
            ret_inss=parsed_data.get('ret_inss'),
            valor_retencoes=parsed_data.get('valor_retencoes'),
            codigo_servico=parsed_data.get('codigo_servico'),
            descricao_servico=parsed_data.get('descricao_servico'),
            status=parsed_data.get('status', 'NORMAL'),
            xml_path=str(xml_path)
        )

        # Salvar no banco (SEMPRE salva para não pular NSU)
        nfse.id = self.nfse_repository.create(nfse)

        # Aplicar evento que tenha chegado antes da nota (cancelamento/substituição)
        self._aplicar_eventos_pendentes(nfse)

    def _aplicar_eventos_pendentes(self, nfse: NFSe) -> None:
        """Aplica à nota recém-salva eventos que chegaram antes dela"""
        try:
            pendentes = self.evento_pendente_repository.get_by_chave(nfse.chave_acesso)
            if not pendentes:
                return

            # O último evento registrado prevalece
            novo_status = pendentes[-1]
            logger.info(f"Aplicando evento pendente {novo_status} à nota {nfse.chave_acesso}")

            nfse.status = novo_status
            if nfse.xml_path:
                novo_caminho = self._mover_arquivo_xml_status(nfse.xml_path, novo_status)
                if novo_caminho:
                    nfse.xml_path = novo_caminho

            self.nfse_repository.update(nfse)

            # Só limpar pendências se a nota já existe para todas as empresas
            # possíveis é impossível de saber; manter o registro é inofensivo
            # (aplicação é idempotente), mas removemos para não acumular.
            self.evento_pendente_repository.delete_by_chave(nfse.chave_acesso)
        except Exception as e:
            logger.error(f"Erro ao aplicar eventos pendentes da chave {nfse.chave_acesso}: {e}")


class DuplicateNFSeError(Exception):
    """Exceção para NFS-e duplicada"""
    pass
