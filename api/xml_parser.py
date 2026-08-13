"""
Parser de XML da NFS-e Nacional
"""
from lxml import etree
from typing import Optional, Dict, Any
from datetime import datetime, date
from decimal import Decimal
import logging

from api.retencoes import extrair_retencoes

logger = logging.getLogger(__name__)


class XMLParser:
    """Parser para extrair dados de XML da NFS-e Nacional"""
    
    # Namespaces comuns em NFS-e
    NAMESPACES = {
        'nfse': 'http://www.abrasf.org.br/nfse',
        'ds': 'http://www.w3.org/2000/09/xmldsig#'
    }
    
    @staticmethod
    def parse_nfse(xml_content: str) -> Optional[Dict[str, Any]]:
        """
        Extrai dados principais de uma NFS-e
        
        Args:
            xml_content: Conteúdo XML da NFS-e
        
        Returns:
            Dicionário com dados extraídos ou None se erro
        """
        try:
            # Parse do XML
            root = etree.fromstring(xml_content.encode('utf-8'))
            
            # Identificar se é um XML de Evento (Cancelamento/Substituição)
            is_evento = False
            root_tag = root.tag.split('}')[-1] if '}' in root.tag else root.tag
            
            if root_tag.lower() in ('resevento', 'evento'):
                is_evento = True
                
            data = {'is_evento': is_evento}
            
            if is_evento:
                # Extrair dados básicos do evento
                chave = XMLParser._get_text(root, './/chNFSe')
                # Obter o tipo do evento: 2 = Cancelamento, 3 = Substituição (ou analisar descEvento/xDesc)
                tp_evento = XMLParser._get_text(root, './/tpEvento')
                desc_evento = XMLParser._get_text(root, './/descEvento') or XMLParser._get_text(root, './/xDesc')
                
                if chave:
                    data['chave_acesso'] = chave
                    
                # Checar primeiro Substituição pois pode estar escrito "Cancelamento por Substituição"
                if tp_evento == '3' or (desc_evento and 'substitui' in desc_evento.lower()):
                    data['status'] = 'SUBSTITUIDA'
                elif tp_evento == '2' or (desc_evento and 'cancelamento' in desc_evento.lower()):
                    data['status'] = 'CANCELADA'
                else:
                    data['status'] = 'MIGRADA' # status padrão de evento desconhecido
                    
                # Eventos não costumam ter os outros dados da nota
                return data
            
            # Continua o parse normal para NFSe
            # Chave de acesso
            chave = XMLParser._get_text(root, './/infNFSe@Id') or \
                    XMLParser._get_text(root, './/chNFSe') or \
                    XMLParser._get_text(root, './/ChaveAcesso')
            
            # Limpar prefixos comuns na chave
            if chave:
                if chave.startswith('NFSe'):
                    chave = chave[4:]
                elif chave.startswith('NFS'):
                    chave = chave[3:]
            data['chave_acesso'] = chave
            
            # Número e série
            data['numero'] = XMLParser._get_text(root, './/nNFSe') or \
                            XMLParser._get_text(root, './/Numero') or \
                            XMLParser._get_text(root, './/NumeroNfse')
            data['serie'] = XMLParser._get_text(root, './/sSerie') or \
                           XMLParser._get_text(root, './/serie') or \
                           XMLParser._get_text(root, './/Serie')
            
            # Número DPS (Declaração de Prestação de Serviço)
            data['numero_dps'] = XMLParser._get_text(root, './/nDPS')
            
            # Datas
            data_emissao_str = XMLParser._get_text(root, './/dtEmi') or \
                              XMLParser._get_text(root, './/DataEmissao') or \
                              XMLParser._get_text(root, './/dhEmi')
            data['data_emissao'] = XMLParser._parse_date(data_emissao_str)
            
            data_comp_str = XMLParser._get_text(root, './/dCompet') or \
                           XMLParser._get_text(root, './/DataCompetencia')
            data['data_competencia'] = XMLParser._parse_date(data_comp_str)
            
            # Prestador
            data['prestador_cnpj'] = XMLParser._get_text(root, './/emit//CNPJ') or \
                                    XMLParser._get_text(root, './/Prestador//Cnpj') or \
                                    XMLParser._get_text(root, './/CpfCnpjPrestador//Cnpj')
            data['prestador_nome'] = XMLParser._get_text(root, './/emit//xNome') or \
                                    XMLParser._get_text(root, './/Prestador//RazaoSocial')
            
            # Tomador
            data['tomador_cnpj'] = XMLParser._get_text(root, './/toma//CNPJ') or \
                                   XMLParser._get_text(root, './/toma//CPF') or \
                                   XMLParser._get_text(root, './/Tomador//Cnpj') or \
                                   XMLParser._get_text(root, './/CpfCnpjTomador//Cnpj')
            data['tomador_nome'] = XMLParser._get_text(root, './/toma//xNome') or \
                                   XMLParser._get_text(root, './/Tomador//RazaoSocial')
            
            # Valores
            valor_servicos_str = XMLParser._get_text(root, './/ValorServicos') or \
                                XMLParser._get_text(root, './/VlServ') or \
                                XMLParser._get_text(root, './/vServ')
            data['valor_servicos'] = XMLParser._parse_decimal(valor_servicos_str)
            
            # No padrão nacional o ISS é vISSQN; vISS/ValorIss são dos layouts antigos.
            # Sem vISSQN aqui o campo ficava zerado em todas as notas.
            valor_iss_str = XMLParser._get_text(root, './/vISSQN') or \
                           XMLParser._get_text(root, './/ValorIss') or \
                           XMLParser._get_text(root, './/VlIss') or \
                           XMLParser._get_text(root, './/vISS')
            data['valor_iss'] = XMLParser._parse_decimal(valor_iss_str)

            # Impostos retidos — regra em api/retencoes.py
            ret = extrair_retencoes(root)
            data['iss_retido'] = ret['iss']
            data['ret_pis'] = ret['pis']
            data['ret_cofins'] = ret['cofins']
            data['ret_irrf'] = ret['irrf']
            data['ret_csll'] = ret['csll']
            data['ret_inss'] = ret['inss']
            data['valor_retencoes'] = ret['total']
            
            # Serviço
            data['codigo_servico'] = XMLParser._get_text(root, './/CodigoServico') or \
                                    XMLParser._get_text(root, './/ItemListaServico')
            
            data['codigo_tributacao_nacional'] = XMLParser._get_text(root, './/cTribNac')
            data['codigo_tributacao_municipal'] = XMLParser._get_text(root, './/cTribMun')
            
            data['descricao_servico'] = XMLParser._get_text(root, './/Discriminacao') or \
                                       XMLParser._get_text(root, './/DiscServ')
            
            # Status
            status = XMLParser._get_text(root, './/Status')
            if status == '2':
                data['status'] = 'CANCELADA'
            elif status == '3':
                data['status'] = 'SUBSTITUIDA'
            else:
                data['status'] = 'NORMAL'
            
            return data
        
        except Exception as e:
            logger.error(f"Erro ao parsear XML: {str(e)}")
            return None
    
    @staticmethod
    def _get_text(element, xpath: str) -> Optional[str]:
        """Extrai texto ou atributo de elemento XML de forma robusta, ignorando namespaces"""
        try:
            # Se o xpath contém '//', podemos ter um prefixo de tag pai (ex: .//emit//CNPJ)
            # Vamos tratar os segmentos do xpath
            parts = [p for p in xpath.split('//') if p and p != '.']
            
            if len(parts) > 1:
                # Caso com hierarquia (ex: emit//CNPJ)
                parent_tag = parts[0]
                child_xpath = '//'.join(parts[1:])
                
                # Encontrar o pai primeiro
                parent = None
                parent_tag_lower = parent_tag.lower()
                for el in element.iter():
                    try:
                        local_name = etree.QName(el).localname
                    except Exception:
                        local_name = el.tag.split('}')[-1] if '}' in el.tag else el.tag
                    
                    if local_name.lower() == parent_tag_lower:
                        parent = el
                        break
                
                if parent is not None:
                    # Buscar o filho dentro do pai
                    return XMLParser._get_text(parent, child_xpath)
                return None

            # Caso base: busca direta (podendo ser atributo)
            tag_to_find = parts[0] if parts else '.'
            
            # Se for uma busca por atributo (ex: @Id)
            attr_to_find = None
            if '@' in tag_to_find:
                tag_to_find, attr_to_find = tag_to_find.split('@')
            
            # Percorrer todos os elementos e encontrar o primeiro com o local-name correspondente
            target_lower = tag_to_find.lower() if tag_to_find and tag_to_find != '.' else None
            
            for el in element.iter():
                try:
                    local_name = etree.QName(el).localname
                except Exception:
                    local_name = el.tag.split('}')[-1] if '}' in el.tag else el.tag
                
                # Caso especial para root (.), se tag_to_find for vazio ou '.'
                is_match = (not target_lower or target_lower == '.') 
                if not is_match:
                    is_match = (local_name.lower() == target_lower)
                
                if is_match:
                    if attr_to_find:
                        # Se procuramos atributo, procurar em attrib (case insensitive)
                        for attr_name, attr_val in el.attrib.items():
                            if attr_name.lower() == attr_to_find.lower():
                                return attr_val.strip() if attr_val else None
                    else:
                        text = el.text
                        return text.strip() if text else None
            
            return None
        except Exception as e:
            logger.debug(f"Erro ao extrair texto do xpath: {e}")
            return None
    
    @staticmethod
    def _parse_date(date_str: Optional[str]) -> Optional[date]:
        """Converte string de data para objeto date"""
        if not date_str:
            return None
        
        try:
            # Tentar formatos comuns
            formats = [
                '%Y-%m-%d',
                '%d/%m/%Y',
                '%Y%m%d',
                '%Y-%m-%dT%H:%M:%S',
                '%Y-%m-%d %H:%M:%S'
            ]
            
            for fmt in formats:
                try:
                    dt = datetime.strptime(date_str[:10] if 'T' in date_str else date_str, fmt)
                    return dt.date()
                except Exception:
                    continue
            
            return None
        except Exception as e:
            logger.debug(f"Erro ao parsear data '{date_str}': {e}")
            return None
    
    @staticmethod
    def _parse_decimal(value_str: Optional[str]) -> Optional[Decimal]:
        """Converte string para Decimal"""
        if not value_str:
            return None
        
        try:
            # Remover espaços e substituir vírgula por ponto
            value_str = value_str.strip().replace(',', '.')
            return Decimal(value_str)
        except Exception as e:
            logger.debug(f"Erro ao converter valor decimal '{value_str}': {e}")
            return None
    
    @staticmethod
    def validate_xml(xml_content: str) -> bool:
        """
        Valida se o XML está bem formado
        
        Args:
            xml_content: Conteúdo XML
        
        Returns:
            True se válido
        """
        try:
            etree.fromstring(xml_content.encode('utf-8'))
            return True
        except Exception as e:
            logger.debug(f"XML inválido: {e}")
            return False
