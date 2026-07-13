"""
API Routes for NFS-e National Custom Web App Backend
"""
import uuid
import threading
import tempfile
import os
import shutil
import logging
import zipfile
import io
from datetime import date, datetime, time as dt_time
from typing import List, Optional
from decimal import Decimal
import pandas as pd

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks, Response
from fastapi.responses import StreamingResponse, FileResponse

import config
from database import Empresa, NFSe, SyncLog
from database.repository import EmpresaRepository, NFSeRepository, SyncLogRepository, SchedulerConfigRepository
from services import EmpresaService, DownloadService, BackupService, get_scheduler
from services.pdf_service import gerar_pdf_nfse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# Thread-safe in-memory store for active background download tasks
active_downloads = {}
active_downloads_lock = threading.Lock()


def run_background_download(download_id: str, empresa_id: int, tipo: str, data_inicio: date, data_fim: date, tipo_periodo: str, reescanear: bool):
    empresa_service = EmpresaService()
    download_service = DownloadService()
    
    empresa = empresa_service.obter_empresa(empresa_id)
    if not empresa:
        with active_downloads_lock:
            active_downloads[download_id] = {
                "status": "erro",
                "mensagem": "Empresa não encontrada",
                "progresso": 1.0,
                "logs": ["Erro: Empresa não encontrada"],
                "stats": {}
            }
        return

    if reescanear:
        empresa.ultimo_nsu = 0
        from database import EmpresaRepository
        EmpresaRepository().update(empresa)
        with active_downloads_lock:
            active_downloads[download_id]["logs"].append("Zerar NSU: Buscando todos os documentos novamente...")

    def update_progress(msg: str):
        with active_downloads_lock:
            if download_id not in active_downloads:
                return
            active_downloads[download_id]["mensagem"] = msg
            active_downloads[download_id]["logs"].append(msg)
            
            # Estimate progress based on callback messages
            if "Processando documento" in msg:
                try:
                    parts = msg.split(" ")
                    fraction = parts[2].split("/")
                    current = int(fraction[0])
                    total = int(fraction[1].replace("...", ""))
                    active_downloads[download_id]["progresso"] = min(0.1 + (current / total) * 0.9, 0.99)
                except Exception:
                    pass
            elif "Encontrados" in msg:
                active_downloads[download_id]["progresso"] = 0.1
            elif "Convertendo" in msg:
                active_downloads[download_id]["progresso"] = 0.02
            elif "Buscando" in msg or "Descobrindo" in msg:
                active_downloads[download_id]["progresso"] = 0.05

    try:
        stats = download_service.download_nfse(
            empresa=empresa,
            tipo=tipo,
            data_inicio=data_inicio,
            data_fim=data_fim,
            tipo_periodo=tipo_periodo,
            callback=update_progress
        )
        with active_downloads_lock:
            active_downloads[download_id]["status"] = "concluido"
            active_downloads[download_id]["progresso"] = 1.0
            active_downloads[download_id]["mensagem"] = "Download concluído com sucesso!"
            active_downloads[download_id]["stats"] = stats
    except Exception as e:
        logger.error(f"Erro no download background: {e}")
        with active_downloads_lock:
            active_downloads[download_id]["status"] = "erro"
            active_downloads[download_id]["progresso"] = 1.0
            active_downloads[download_id]["mensagem"] = f"Erro: {str(e)}"
            active_downloads[download_id]["logs"].append(f"Erro crítico: {str(e)}")


def run_background_lote(download_id: str, tipo: str, data_inicio: date, data_fim: date, tipo_periodo: str):
    empresa_service = EmpresaService()
    download_service = DownloadService()
    empresas = empresa_service.listar_empresas(apenas_ativas=True)
    
    if not empresas:
        with active_downloads_lock:
            active_downloads[download_id] = {
                "status": "erro",
                "mensagem": "Nenhuma empresa cadastrada",
                "progresso": 1.0,
                "logs": ["Nenhuma empresa cadastrada para sincronização."],
                "stats": {}
            }
        return

    total_empresas = len(empresas)
    resultados = []
    total_novas = 0
    total_erros = 0

    for idx, empresa in enumerate(empresas):
        emp_progress_base = idx / total_empresas
        with active_downloads_lock:
            active_downloads[download_id]["mensagem"] = f"Sincronizando {empresa.razao_social}..."
            active_downloads[download_id]["logs"].append(f"▶️ Sincronizando empresa {idx+1}/{total_empresas}: {empresa.razao_social}...")
            active_downloads[download_id]["progresso"] = emp_progress_base

        def callback_lote(msg: str):
            with active_downloads_lock:
                active_downloads[download_id]["logs"].append(f"  ↳ {msg}")
                if "Processando documento" in msg:
                    try:
                        parts = msg.split(" ")
                        fraction = parts[2].split("/")
                        current = int(fraction[0])
                        total = int(fraction[1].replace("...", ""))
                        active_downloads[download_id]["progresso"] = emp_progress_base + (current / total) * (1 / total_empresas) * 0.9
                    except Exception:
                        pass

        try:
            stats = download_service.download_nfse(
                empresa=empresa,
                tipo=tipo,
                data_inicio=data_inicio,
                data_fim=data_fim,
                tipo_periodo=tipo_periodo,
                callback=callback_lote
            )
            resultados.append({
                'empresa': empresa.razao_social,
                'cnpj': empresa.cnpj_formatado,
                'total': stats['total_encontradas'],
                'novas': stats['novas'],
                'duplicadas': stats['duplicadas'],
                'erros': stats['erros'],
                'status': 'sucesso' if stats['erros'] == 0 else 'alerta'
            })
            total_novas += stats['novas']
            total_erros += stats['erros']
        except Exception as e:
            resultados.append({
                'empresa': empresa.razao_social,
                'cnpj': empresa.cnpj_formatado,
                'total': 0,
                'novas': 0,
                'duplicadas': 0,
                'erros': 1,
                'status': 'erro',
                'erro_detalhe': str(e)
            })
            total_erros += 1
            with active_downloads_lock:
                active_downloads[download_id]["logs"].append(f"❌ Erro na empresa {empresa.razao_social}: {str(e)}")

    with active_downloads_lock:
        active_downloads[download_id]["status"] = "concluido"
        active_downloads[download_id]["progresso"] = 1.0
        active_downloads[download_id]["mensagem"] = f"Sincronização concluída! {total_novas} notas novas baixadas."
        active_downloads[download_id]["stats"] = {
            "total_novas": total_novas,
            "total_erros": total_erros,
            "resultados": resultados
        }


def run_background_status_sync(download_id: str, nota_ids: List[int]):
    empresa_service = EmpresaService()
    download_service = DownloadService()
    nfse_repository = NFSeRepository()
    
    with active_downloads_lock:
        active_downloads[download_id]["mensagem"] = "Carregando notas..."
        active_downloads[download_id]["logs"].append("Iniciando sincronização de status...")

    all_notes = nfse_repository.get_all(texto_busca=None)
    notes_to_sync = [n for n in all_notes if n.id in nota_ids]
    
    if not notes_to_sync:
        with active_downloads_lock:
            active_downloads[download_id]["status"] = "erro"
            active_downloads[download_id]["mensagem"] = "Nenhuma nota encontrada para sincronizar"
            active_downloads[download_id]["progresso"] = 1.0
        return

    # Group notes by empresa_id
    notes_by_empresa = {}
    for n in notes_to_sync:
        notes_by_empresa.setdefault(n.empresa_id, []).append(n)
        
    total_notes = len(notes_to_sync)
    counter = 0
    updated_count = 0
    error_count = 0

    for emp_id, emp_notes in notes_by_empresa.items():
        empresa = empresa_service.obter_empresa(emp_id)
        if not empresa:
            counter += len(emp_notes)
            continue
            
        with active_downloads_lock:
            active_downloads[download_id]["logs"].append(f"Iniciando consulta para {empresa.razao_social} ({len(emp_notes)} notas)...")
            
        def callback_sync(msg: str):
            nonlocal counter
            with active_downloads_lock:
                active_downloads[download_id]["mensagem"] = f"{empresa.razao_social}: {msg}"
                if "Consultando status" in msg:
                    # e.g. "Consultando status da nota X/Y..."
                    try:
                        subparts = msg.split(" ")
                        fraction = subparts[4].split("/")
                        curr_fraction = int(fraction[0])
                        active_downloads[download_id]["progresso"] = min((counter + curr_fraction - 1) / total_notes, 0.99)
                    except Exception:
                        pass

        try:
            res = download_service.sincronizar_status_notas(emp_notes, empresa, callback=callback_sync)
            updated_count += res.get('atualizadas', 0)
            error_count += res.get('erros', 0)
            counter += len(emp_notes)
        except Exception as e:
            error_count += len(emp_notes)
            counter += len(emp_notes)
            with active_downloads_lock:
                active_downloads[download_id]["logs"].append(f"Erro em {empresa.razao_social}: {e}")

    with active_downloads_lock:
        active_downloads[download_id]["status"] = "concluido"
        active_downloads[download_id]["progresso"] = 1.0
        active_downloads[download_id]["mensagem"] = f"Sincronização de status concluída! {updated_count} status atualizados."
        active_downloads[download_id]["stats"] = {
            "atualizadas": updated_count,
            "erros": error_count
        }


# --- EMPRESAS ---

@router.get("/empresas")
def listar_empresas(ativas_apenas: bool = False):
    empresa_service = EmpresaService()
    empresas = empresa_service.listar_empresas(apenas_ativas=ativas_apenas)
    result = []
    for emp in empresas:
        d = emp.to_dict()
        d["cnpj_formatado"] = emp.cnpj_formatado
        
        # Validar validade do certificado digital
        try:
            cert_info = empresa_service.validar_certificado_empresa(emp.id)
            d["certificado_valido"] = cert_info.get("valid", False)
            d["certificado_expirado"] = cert_info.get("is_expired", True)
            if cert_info.get("expiry_date"):
                d["certificado_vencimento"] = cert_info["expiry_date"].strftime("%d/%m/%Y %H:%M")
                d["certificado_dias_restantes"] = (cert_info["expiry_date"] - datetime.now()).days
            else:
                d["certificado_vencimento"] = "Inválido/Erro"
                d["certificado_dias_restantes"] = -1
        except Exception as e:
            d["certificado_valido"] = False
            d["certificado_expirado"] = True
            d["certificado_vencimento"] = f"Erro: {str(e)}"
            d["certificado_dias_restantes"] = -1
            
        result.append(d)
    return result


@router.post("/empresas")
def cadastrar_empresa(
    cnpj: str = Form(...),
    razao_social: str = Form(...),
    nome_fantasia: Optional[str] = Form(None),
    certificado_senha: str = Form(...),
    certificado: UploadFile = File(...)
):
    empresa_service = EmpresaService()
    # Save UploadFile to a temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pfx") as tmp:
        shutil.copyfileobj(certificado.file, tmp)
        tmp_path = tmp.name

    try:
        res = empresa_service.cadastrar_empresa(
            cnpj=cnpj,
            razao_social=razao_social,
            nome_fantasia=nome_fantasia,
            certificado_path=tmp_path,
            certificado_senha=certificado_senha
        )
        if not res.get("success"):
            raise HTTPException(status_code=400, detail=res.get("error", "Erro ao cadastrar empresa"))
        return res
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


@router.put("/empresas/{empresa_id}")
def atualizar_empresa(
    empresa_id: int,
    razao_social: str = Form(...),
    nome_fantasia: Optional[str] = Form(None),
    ativo: bool = Form(...),
    certificado_senha: Optional[str] = Form(None),
    certificado: Optional[UploadFile] = File(None)
):
    empresa_service = EmpresaService()
    empresa = empresa_service.obter_empresa(empresa_id)
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")

    empresa.razao_social = razao_social
    empresa.nome_fantasia = nome_fantasia
    empresa.ativo = ativo

    if certificado and certificado_senha:
        # Save UploadFile to a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pfx") as tmp:
            shutil.copyfileobj(certificado.file, tmp)
            tmp_path = tmp.name
        try:
            # Validate certificate first
            from api import CertificateManager
            cert_manager = CertificateManager()
            cert_info = cert_manager.validate_certificate(tmp_path, certificado_senha)
            if not cert_info.get('valid'):
                raise HTTPException(status_code=400, detail=f"Certificado inválido: {cert_info.get('error')}")
            
            # Exclude old certificate physical file
            if empresa.certificado_path:
                try:
                    os.unlink(empresa.certificado_path)
                except Exception:
                    pass
            
            # Copy new certificate to secure data folder
            cert_dest = config.CERTIFICADOS_DIR / f"{empresa.cnpj}.pfx"
            shutil.copy2(tmp_path, cert_dest)
            empresa.certificado_path = str(cert_dest)
            empresa.certificado_senha = certificado_senha
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    elif certificado_senha:
        empresa.certificado_senha = certificado_senha

    res = empresa_service.atualizar_empresa(empresa)
    return {"success": res}


@router.delete("/empresas/{empresa_id}")
def excluir_empresa(empresa_id: int):
    empresa_service = EmpresaService()
    res = empresa_service.excluir_empresa(empresa_id)
    if not res:
        raise HTTPException(status_code=400, detail="Erro ao excluir empresa")
    return {"success": True}


# --- DOWNLOADS ---

@router.post("/downloads/iniciar")
def iniciar_download(
    background_tasks: BackgroundTasks,
    empresa_id: int = Form(...),
    tipo: str = Form(...),
    data_inicio: str = Form(...),
    data_fim: str = Form(...),
    tipo_periodo: str = Form(...),
    reescanear: bool = Form(False)
):
    dt_inicio = date.fromisoformat(data_inicio)
    dt_fim = date.fromisoformat(data_fim)
    
    download_id = str(uuid.uuid4())
    
    with active_downloads_lock:
        active_downloads[download_id] = {
            "status": "rodando",
            "mensagem": "Iniciando download...",
            "progresso": 0.0,
            "logs": ["Tarefa criada. Conectando com a API da Receita Federal..."],
            "stats": {}
        }
        
    background_tasks.add_task(
        run_background_download,
        download_id=download_id,
        empresa_id=empresa_id,
        tipo=tipo,
        data_inicio=dt_inicio,
        data_fim=dt_fim,
        tipo_periodo=tipo_periodo,
        reescanear=reescanear
    )
    return {"download_id": download_id}


@router.post("/downloads/lote")
def iniciar_download_lote(
    background_tasks: BackgroundTasks,
    tipo: str = Form(...),
    data_inicio: str = Form(...),
    data_fim: str = Form(...),
    tipo_periodo: str = Form(...)
):
    dt_inicio = date.fromisoformat(data_inicio)
    dt_fim = date.fromisoformat(data_fim)
    
    download_id = str(uuid.uuid4())
    
    with active_downloads_lock:
        active_downloads[download_id] = {
            "status": "rodando",
            "mensagem": "Iniciando sincronização em lote...",
            "progresso": 0.0,
            "logs": ["Sincronização em lote criada."],
            "stats": {}
        }
        
    background_tasks.add_task(
        run_background_lote,
        download_id=download_id,
        tipo=tipo,
        data_inicio=dt_inicio,
        data_fim=dt_fim,
        tipo_periodo=tipo_periodo
    )
    return {"download_id": download_id}


@router.get("/downloads/status/{download_id}")
def obter_status_download(download_id: str):
    with active_downloads_lock:
        if download_id not in active_downloads:
            raise HTTPException(status_code=404, detail="Tarefa de download não encontrada")
        return active_downloads[download_id]


@router.post("/downloads/importar")
def importar_xmls(
    empresa_id: int = Form(...),
    xml_files: List[UploadFile] = File(...)
):
    from api import XMLParser
    empresa_service = EmpresaService()
    download_service = DownloadService()
    nfse_repo = NFSeRepository()
    xml_parser = XMLParser()

    empresa = empresa_service.obter_empresa(empresa_id)
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")

    stats = {'importadas': 0, 'duplicadas': 0, 'erros': 0, 'detalhes': []}
    
    for file in xml_files:
        try:
            content_bytes = file.file.read()
            xml_content = content_bytes.decode('utf-8')
            
            parsed = xml_parser.parse_nfse(xml_content)
            if not parsed:
                stats['erros'] += 1
                stats['detalhes'].append(f"{file.filename}: Erro ao parsear XML")
                continue
            
            if parsed.get('is_evento'):
                stats['erros'] += 1
                stats['detalhes'].append(f"{file.filename}: É um evento, não uma NFS-e")
                continue
            
            chave = parsed.get('chave_acesso')
            if nfse_repo.exists_by_chave(chave, empresa_id=empresa_id):
                stats['duplicadas'] += 1
                stats['detalhes'].append(f"{file.filename}: Nota já existe no banco para esta empresa")
                continue
            
            prestador = (parsed.get('prestador_cnpj') or '').replace('.', '').replace('/', '').replace('-', '')
            tomador = (parsed.get('tomador_cnpj') or '').replace('.', '').replace('/', '').replace('-', '')
            
            if prestador == empresa.cnpj:
                tipo_nfse = 'EMITIDA'
            elif tomador == empresa.cnpj:
                tipo_nfse = 'RECEBIDA'
            else:
                stats['erros'] += 1
                stats['detalhes'].append(f"{file.filename}: CNPJ da empresa não coincide com prestador nem tomador")
                continue
            
            download_service._processar_nfse(parsed, empresa, tipo_nfse, xml_content)
            stats['importadas'] += 1
        except Exception as e:
            stats['erros'] += 1
            stats['detalhes'].append(f"{file.filename}: {str(e)}")

    return stats


# --- NOTAS FISCAIS ---

@router.get("/notas")
def listar_notas(
    empresa_id: Optional[int] = None,
    tipo: Optional[str] = None,
    data_inicio: Optional[str] = None,
    data_fim: Optional[str] = None,
    campo_data: str = 'emissao',
    texto_busca: Optional[str] = None,
    page: int = 1,
    limit: int = 50
):
    nfse_repository = NFSeRepository()
    
    dt_inicio = date.fromisoformat(data_inicio) if data_inicio else None
    dt_fim = date.fromisoformat(data_fim) if data_fim else None
    
    status = None
    query_tipo = None
    if tipo == "EMITIDA":
        query_tipo = "EMITIDA"
        status = "NORMAL"
    elif tipo == "RECEBIDA":
        query_tipo = "RECEBIDA"
        status = "NORMAL"
    elif tipo == "CANCELADA":
        status = "CANCELADA"
    elif tipo == "SUBSTITUIDA":
        status = "SUBSTITUIDA"

    campo_db = 'data_emissao' if campo_data == 'emissao' else 'data_competencia'

    # Fetch all matching
    all_notes = nfse_repository.get_all(
        empresa_id=empresa_id,
        tipo=query_tipo,
        status=status,
        data_inicio=dt_inicio,
        data_fim=dt_fim,
        campo_data=campo_db,
        texto_busca=texto_busca
    )
    
    total_notes = len(all_notes)
    
    # Calculate statistics on the filtered set
    total_valor = sum(float(n.valor_servicos or 0) for n in all_notes)
    emitidas = sum(1 for n in all_notes if n.tipo == "EMITIDA")
    recebidas = sum(1 for n in all_notes if n.tipo == "RECEBIDA")
    
    # Paginate
    start_idx = (page - 1) * limit
    end_idx = start_idx + limit
    paginated_notes = all_notes[start_idx:end_idx]
    
    # Convert notes to dict
    notes_dict = []
    for n in paginated_notes:
        d = n.to_dict()
        d["prestador_cnpj_formatado"] = n.prestador_cnpj_formatado
        d["tomador_cnpj_formatado"] = n.tomador_cnpj_formatado
        notes_dict.append(d)

    # Detect gaps if filtered by a single company
    gaps_info = None
    if empresa_id:
        gaps = nfse_repository.detectar_gaps_numeracao(empresa_id)
        if gaps['numeros_faltantes']:
            gaps_info = {
                "total_faltantes": len(gaps['numeros_faltantes']),
                "numeros": gaps['numeros_faltantes'][:15],  # limit list
                "primeiro": gaps['primeiro'],
                "ultimo": gaps['ultimo']
            }

    return {
        "total": total_notes,
        "page": page,
        "limit": limit,
        "notas": notes_dict,
        "estatisticas": {
            "total_notas": total_notes,
            "total_emitidas": emitidas,
            "total_recebidas": recebidas,
            "valor_total": total_valor
        },
        "gaps": gaps_info
    }


@router.post("/notas/buscar-faltantes")
def buscar_notas_faltantes(empresa_id: int = Form(...)):
    """
    Busca ativa de notas faltantes: consulta a SEFIN Nacional para cada
    lacuna de numeração DPS das notas emitidas da empresa e recupera as
    notas que existem lá mas não foram distribuídas/baixadas.
    """
    empresa_service = EmpresaService()
    empresa = empresa_service.obter_empresa(empresa_id)
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")

    download_service = DownloadService()
    stats = download_service.buscar_notas_faltantes(empresa)
    return stats


@router.post("/notas/sincronizar")
def sincronizar_notas(
    background_tasks: BackgroundTasks,
    nota_ids: List[int]
):
    download_id = str(uuid.uuid4())
    with active_downloads_lock:
        active_downloads[download_id] = {
            "status": "rodando",
            "mensagem": "Iniciando atualização de status das notas selecionadas...",
            "progresso": 0.0,
            "logs": ["Iniciando conexão para consultar eventos na API Nacional..."],
            "stats": {}
        }
    background_tasks.add_task(run_background_status_sync, download_id=download_id, nota_ids=nota_ids)
    return {"download_id": download_id}


@router.get("/notas/{nota_id}/xml")
def baixar_xml(nota_id: int):
    nfse_repo = NFSeRepository()
    # To find by id, let's search in all notes
    all_notes = nfse_repo.get_all(texto_busca=None)
    note = next((n for n in all_notes if n.id == nota_id), None)
    
    if not note or not note.xml_path:
        raise HTTPException(status_code=404, detail="XML não encontrado")
    
    if not os.path.exists(note.xml_path):
        raise HTTPException(status_code=404, detail="Arquivo XML físico não encontrado")
        
    return FileResponse(
        path=note.xml_path,
        filename=f"{note.numero or 'nota'}_{note.chave_acesso[:10]}.xml",
        media_type="application/xml"
    )


@router.get("/notas/{nota_id}/pdf")
def visualizar_pdf(nota_id: int):
    nfse_repo = NFSeRepository()
    all_notes = nfse_repo.get_all(texto_busca=None)
    note = next((n for n in all_notes if n.id == nota_id), None)
    
    if not note or not note.xml_path or not os.path.exists(note.xml_path):
        raise HTTPException(status_code=404, detail="XML físico para gerar o PDF não encontrado")

    try:
        with open(note.xml_path, 'r', encoding='utf-8') as f:
            xml_content = f.read()
        pdf_bytes = gerar_pdf_nfse(xml_content)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"inline; filename=NFS-e_{note.numero or 'nota'}.pdf"
            }
        )
    except Exception as e:
        logger.error(f"Erro ao gerar PDF: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao gerar PDF: {str(e)}")


@router.post("/notas/exportar")
def exportar_notas(
    nota_ids: List[int],
    formato: str
):
    nfse_repo = NFSeRepository()
    all_notes = nfse_repo.get_all(texto_busca=None)
    selected_notes = [n for n in all_notes if n.id in nota_ids]
    
    if not selected_notes:
        raise HTTPException(status_code=400, detail="Nenhuma nota selecionada")

    if formato == "excel":
        export_data = []
        for n in selected_notes:
            export_data.append({
                'Número': n.numero or 'N/A',
                'DPS': n.numero_dps or 'N/A',
                'Série': n.serie or 'N/A',
                'Tipo': n.tipo,
                'Data Emissão': n.data_emissao.strftime('%d/%m/%Y') if n.data_emissao else 'N/A',
                'Prestador': n.prestador_nome or n.prestador_cnpj_formatado or 'N/A',
                'Tomador': n.tomador_nome or n.tomador_cnpj_formatado or 'N/A',
                'Valor': float(n.valor_servicos or 0),
                'Valor ISS': float(n.valor_iss or 0),
                'Código Tributação Nacional': n.codigo_tributacao_nacional or 'N/A',
                'Código Tributação Municipal': n.codigo_tributacao_municipal or 'N/A',
                'Status': n.status,
            })
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            pd.DataFrame(export_data).to_excel(writer, index=False, sheet_name='NFS-e')
            
        return Response(
            content=output.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=nfse_{date.today().strftime('%Y%m%d')}.xlsx"}
        )

    elif formato == "xml":
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for n in selected_notes:
                if n.xml_path and os.path.exists(n.xml_path):
                    zip_file.write(n.xml_path, f"{n.numero or 'nota'}_{n.chave_acesso[:20]}.xml")
                    
        return Response(
            content=zip_buffer.getvalue(),
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename=xmls_{date.today().strftime('%Y%m%d')}.zip"}
        )

    elif formato == "pdf":
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for n in selected_notes:
                if n.xml_path and os.path.exists(n.xml_path):
                    try:
                        with open(n.xml_path, 'r', encoding='utf-8') as f:
                            xml_content = f.read()
                        pdf_bytes = gerar_pdf_nfse(xml_content)
                        pdf_name = f"NFS-e_{n.numero or 'nota'}_{n.chave_acesso[:10]}.pdf"
                        zip_file.writestr(pdf_name, pdf_bytes)
                    except Exception:
                        pass
                        
        return Response(
            content=zip_buffer.getvalue(),
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename=pdfs_{date.today().strftime('%Y%m%d')}.zip"}
        )

    else:
        raise HTTPException(status_code=400, detail="Formato inválido")


# --- AGENDADOR ---

@router.get("/agendador/status")
def obter_status_agendador():
    scheduler = get_scheduler()
    status = scheduler.get_status()
    
    # Process scheduler logs
    historico = scheduler.get_historico(limit=50)
    history_list = []
    for log in historico:
        duracao = ""
        if log.started_at and log.finished_at:
            delta = log.finished_at - log.started_at
            duracao = f"{delta.total_seconds():.0f}s"
            
        history_list.append({
            'id': log.id,
            'data': log.started_at.strftime('%d/%m/%Y %H:%M') if log.started_at else '',
            'empresa_nome': log.empresa_nome,
            'tipo_operacao': log.tipo_operacao,
            'notas_encontradas': log.notas_encontradas,
            'notas_novas': log.notas_novas,
            'status_atualizados': log.status_atualizados,
            'erros': log.erros,
            'duracao': duracao,
            'detalhes': log.detalhes or ''
        })
        
    proximo_run_str = status['proximo_run'].strftime('%d/%m/%Y %H:%M') if status['proximo_run'] else None
    ultimo_run_str = status['ultimo_run'].strftime('%d/%m/%Y %H:%M') if status['ultimo_run'] else None
    
    # Build complete backward and forward-compatible structure
    res = {
        'ativo': status['ativo'],
        'scheduler_ativo': status['ativo'],
        'modo': status['modo'],
        'intervalo_horas': status['intervalo_horas'],
        'horario': status['horario'],
        'proximo_run': proximo_run_str,
        'proxima_execucao': proximo_run_str or 'Indefinida/Manual',
        'ultimo_run': ultimo_run_str,
        'executando': status['executando'],
        'config': {
            'modo': status['modo'],
            'intervalo_horas': status['intervalo_horas'],
            'horario': status['horario']
        },
        'historico': history_list
    }
    return res


@router.post("/agendador/configurar")
def configurar_agendador(
    ativo: bool = Form(...),
    modo: str = Form(...),
    intervalo_horas: int = Form(...),
    horario: str = Form(...)
):
    scheduler = get_scheduler()
    if ativo:
        success = scheduler.iniciar(intervalo_horas=intervalo_horas, modo=modo, horario=horario)
        if not success:
            raise HTTPException(status_code=400, detail="Erro ao ativar agendador")
    else:
        scheduler.parar()
    return {"success": True}


@router.post("/agendador/executar")
def executar_agendador_agora(background_tasks: BackgroundTasks):
    scheduler = get_scheduler()
    status = scheduler.get_status()
    if status['executando']:
        raise HTTPException(status_code=400, detail="Sincronização automática já em andamento")

    # Run in background task to avoid timeout
    def run_sync():
        try:
            scheduler.executar_agora()
        except Exception as e:
            logger.error(f"Erro ao executar scheduler manualmente: {e}")

    background_tasks.add_task(run_sync)
    return {"success": True, "message": "Sincronização disparada com sucesso em segundo plano!"}


# --- BACKUPS ---

@router.get("/backup")
def listar_backups():
    backup_service = BackupService()
    backups = backup_service.listar_backups()
    res = []
    for b in backups:
        res.append({
            'nome': b['nome'],
            'data': b['data'].strftime('%d/%m/%Y %H:%M'),
            'tamanho_mb': b['tamanho_mb'],
            'tamanho_bytes': b['tamanho_bytes']
        })
    return res


@router.post("/backup/criar")
def criar_backup():
    backup_service = BackupService()
    try:
        zip_path = backup_service.criar_backup()
        tamanho_mb = zip_path.stat().st_size / (1024 * 1024)
        return {
            "success": True,
            "nome": zip_path.name,
            "tamanho_mb": round(tamanho_mb, 2)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao criar backup: {str(e)}")


@router.get("/backup/baixar/{nome_backup}")
def baixar_arquivo_backup(nome_backup: str):
    backup_service = BackupService()
    backups = backup_service.listar_backups()
    selected = next((b for b in backups if b['nome'] == nome_backup), None)
    
    if not selected or not os.path.exists(selected['caminho']):
        raise HTTPException(status_code=404, detail="Backup físico não encontrado")
        
    return FileResponse(
        path=selected['caminho'],
        filename=selected['nome'],
        media_type="application/zip"
    )


@router.post("/backup/restaurar")
def restaurar_backup(
    nome_backup: Optional[str] = Form(None),
    backup_file: Optional[UploadFile] = File(None)
):
    backup_service = BackupService()
    
    if backup_file:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
            shutil.copyfileobj(backup_file.file, tmp)
            tmp_path = tmp.name
        try:
            stats = backup_service.restaurar_backup(tmp_path)
            return {"success": True, "stats": stats}
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Erro ao restaurar: {str(e)}")
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    elif nome_backup:
        backups = backup_service.listar_backups()
        selected = next((b for b in backups if b['nome'] == nome_backup), None)
        if not selected:
            raise HTTPException(status_code=404, detail="Backup não encontrado")
        try:
            stats = backup_service.restaurar_backup(selected['caminho'])
            return {"success": True, "stats": stats}
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Erro ao restaurar: {str(e)}")
    else:
        raise HTTPException(status_code=400, detail="Informe o nome do backup local ou envie um arquivo")


# --- TESTE API ---

@router.post("/teste-api")
def testar_conexao_api(empresa_id: int = Form(...)):
    from api import CertificateManager, NFSeClient
    empresa_service = EmpresaService()
    empresa = empresa_service.obter_empresa(empresa_id)
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")

    try:
        cert_manager = CertificateManager()
        cert_path, key_path = cert_manager.convert_pfx_to_pem(
            empresa.certificado_path,
            empresa.certificado_senha
        )
        
        client = NFSeClient(cert_path, key_path)
        resultado = client.buscar_por_nsu(0, cnpj_consulta=empresa.cnpj, lote=True)
        
        cert_manager.cleanup_temp_files(empresa.cnpj)
        
        if resultado:
            status = resultado.get('StatusProcessamento')
            erros_res = []
            if status == 'REJEICAO':
                erros = resultado.get('Erros', [])
                for erro in erros:
                    erros_res.append(f"{erro.get('Codigo')}: {erro.get('Descricao')}")
            
            return {
                "success": True,
                "status": status,
                "documentos_encontrados": len(resultado.get('LoteDFe', [])) if status == 'DOCUMENTOS_LOCALIZADOS' else 0,
                "erros": erros_res,
                "resposta_completa": resultado
            }
        else:
            return {
                "success": False,
                "error": "API respondeu com status vazio (404)"
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


# --- DASHBOARD / ANALYTICS ---

@router.get("/dashboard/estatisticas")
def obter_estatisticas_dashboard(empresa_id: Optional[int] = None):
    nfse_repo = NFSeRepository()
    emp_service = EmpresaService()
    
    # Active companies list
    active_companies = emp_service.listar_empresas(apenas_ativas=True)
    stats = nfse_repo.get_statistics(empresa_id)
    
    # Build logs count
    scheduler = get_scheduler()
    logs = scheduler.get_historico(limit=10)
    erros_recentes = sum(1 for l in logs if l.erros > 0)

    # Format values
    valor_total_emitido = float(stats.get('valor_total_emitido') or 0.0)
    valor_total_recebido = float(stats.get('valor_total_recebido') or 0.0)

    return {
        "total_notas": stats.get('total', 0),
        "total_emitidas": stats.get('total_emitidas', 0),
        "total_recebidas": stats.get('total_recebidas', 0),
        "valor_total_emitido": valor_total_emitido,
        "valor_total_recebido": valor_total_recebido,
        "total_empresas": len(active_companies),
        "erros_recentes": erros_recentes
    }


@router.get("/dashboard/faturamento")
def obter_grafico_faturamento(ano: Optional[int] = None):
    if not ano:
        ano = datetime.now().year

    nfse_repo = NFSeRepository()
    emp_service = EmpresaService()
    empresas = emp_service.listar_empresas(apenas_ativas=True)
    
    # Initialize empty month bins
    meses_res = {m: 0.0 for m in range(1, 12 + 1)}
    
    # Query all normal, emitted notes for this year
    all_notes = []
    for emp in empresas:
        notes = nfse_repo.get_all(
            empresa_id=emp.id,
            tipo="EMITIDA",
            status="NORMAL",
            data_inicio=date(ano, 1, 1),
            data_fim=date(ano, 12, 31),
            campo_data="data_competencia"
        )
        all_notes.extend(notes)
        
    for n in all_notes:
        if n.data_competencia and n.data_competencia.year == ano:
            m = n.data_competencia.month
            meses_res[m] += float(n.valor_servicos or 0.0)
            
    # Chart format
    faturamento_mensal = []
    meses_nomes = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
    for m in range(1, 13):
        faturamento_mensal.append({
            "mes": meses_nomes[m - 1],
            "mes_num": m,
            "valor": round(meses_res[m], 2)
        })
        
    # Faturamento by company (for table)
    faturamento_empresas = []
    hoje = datetime.now()
    cur_mes = hoje.month
    
    for emp in empresas:
        notes_mes = nfse_repo.get_all(
            empresa_id=emp.id,
            tipo="EMITIDA",
            status="NORMAL",
            data_inicio=date(ano, cur_mes, 1),
            data_fim=date(ano, cur_mes, 28), # safe lower bound or month end
            campo_data="data_competencia"
        )
        val = sum(float(x.valor_servicos or 0.0) for x in notes_mes)
        faturamento_empresas.append({
            "empresa": emp.razao_social,
            "cnpj": emp.cnpj_formatado,
            "notas": len(notes_mes),
            "valor": round(val, 2)
        })

    return {
        "ano": ano,
        "faturamento_mensal": faturamento_mensal,
        "faturamento_empresas": faturamento_empresas
    }


# --- CONFIGURATION & AUTO-UPDATER ENDPOINTS ---

@router.get("/config/xmls_dir")
def obter_xmls_dir():
    config_repo = SchedulerConfigRepository()
    return {"xmls_dir": config_repo.get("xmls_dir", "")}


@router.post("/config/xmls_dir")
def salvar_xmls_dir(xmls_dir: str = Form(...)):
    import os
    xmls_dir = xmls_dir.strip()
    
    if xmls_dir and not os.path.exists(xmls_dir):
        try:
            os.makedirs(xmls_dir, exist_ok=True)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Caminho inválido ou sem permissão de gravação: {str(e)}")
            
    config_repo = SchedulerConfigRepository()
    config_repo.set("xmls_dir", xmls_dir)
    return {"success": True, "xmls_dir": xmls_dir}


def _versao_tupla(v):
    """Converte '1.2.3' em (1, 2, 3) para comparação numérica correta.
    Evita a armadilha da comparação de texto, onde '1.10' < '1.9'."""
    try:
        return tuple(int(p) for p in str(v).strip().split("."))
    except (ValueError, AttributeError):
        return (0,)


@router.get("/atualizador/checar")
def checar_atualizacao():
    versao_local = "1.2"
    try:
        import requests
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        url = config.GITHUB_UPDATE_URL
        # Ignora verificação SSL para garantir compatibilidade com Python embutido/portátil no Windows
        response = requests.get(url, timeout=3.0, verify=False)
        if response.ok:
            data = response.json()
            versao_remota = data.get("versao", "1.0")
            # Compara versões numericamente (1.10 > 1.9)
            update_disponivel = _versao_tupla(versao_remota) > _versao_tupla(versao_local)
            return {
                "success": True,
                "versao_local": versao_local,
                "versao_remota": versao_remota,
                "update_disponivel": update_disponivel,
                "notas_versao": data.get("notas_versao", ""),
                "url_download": data.get("url_download", "")
            }
    except Exception as e:
        logger.error(f"❌ Erro ao buscar atualizacoes no GitHub: {str(e)}")
        print(f"❌ Erro ao buscar atualizacoes no GitHub: {str(e)}")
        
    return {
        "success": True,
        "versao_local": versao_local,
        "versao_remota": versao_local,
        "update_disponivel": False,
        "notas_versao": "Nenhuma atualização disponível no momento.",
        "url_download": ""
    }


@router.post("/atualizador/executar")
def executar_atualizacao(url_download: str = Form(...)):
    import subprocess
    import sys
    import os
    import requests
    import threading
    import time
    
    if not url_download:
        raise HTTPException(status_code=400, detail="URL de download não fornecida.")
        
    try:
        temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "temp")
        os.makedirs(temp_dir, exist_ok=True)
        zip_path = os.path.join(temp_dir, "update.zip")
        
        # Download update zip com verify=False para garantir portabilidade de SSL
        response = requests.get(url_download, timeout=30.0, verify=False)
        if not response.ok:
            raise Exception("Falha ao efetuar download da atualização.")
            
        with open(zip_path, "wb") as f:
            f.write(response.content)
            
        # Get python executable (ensure pythonw for headless)
        python_exe = sys.executable
        if "pythonw" in python_exe.lower():
            pass
        elif "python.exe" in python_exe.lower():
            python_exe = python_exe.replace("python.exe", "pythonw.exe")
        elif "python" in python_exe.lower():
            python_exe = python_exe.replace("python", "pythonw")
            
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Spawn updater.py in background detached
        cmd = [python_exe, "updater.py", zip_path]
        creationflags = 0x00000008 | 0x00000200
        
        subprocess.Popen(
            cmd,
            cwd=current_dir,
            creationflags=creationflags,
            close_fds=True
        )
        
        # Threaded exit to allow browser to receive successful response before server shuts down
        def shutdown_server():
            time.sleep(1.0)
            logger.info("⏹️ Desligando servidor FastAPI para auto-atualização de arquivos...")
            os._exit(0)
            
        threading.Thread(target=shutdown_server, daemon=True).start()
        
        return {"success": True, "message": "Atualização em andamento. O sistema irá reiniciar em instantes."}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar auto-atualização: {str(e)}")

