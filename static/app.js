/* ==========================================================================
   APP.JS - MOTOR DO FRONTEND SPA PORTAL NFS-E (MATERIAL DESIGN 3)
   ========================================================================== */

// 1. ESTADO GLOBAL DA APLICAÇÃO
const AppState = {
    empresas: [],
    activeCompanyId: null,
    currentView: 'dashboard',
    notesPage: 1,
    notesLimit: 50,
    selectedNotas: new Set(),
    faturamentoChart: null,
    downloadPollingInterval: null,
    schedulerPollingInterval: null,
    lastPolledLogIndex: 0,
    faturamentoFilterType: 'competencia', // 'competencia' ou 'emissao'
    faturamentoReportNotes: [], // Armazena notas carregadas na apuração mensal
    allNotas: [], // Armazena todas as notas carregadas da busca atual
    columnFilters: {
        numero: '',
        numero_dps: '',
        serie: '',
        data_emissao: '',
        prestador_nome: '',
        tomador_nome: '',
        valor_servicos: '',
        status: ''
    },
    sortColumn: null,
    sortOrder: 'asc',
    notifications: [],
    unreadNotificationsCount: 0
};

// Sinalizador para evitar spam de alertas de certificado no boot
let hasShownBootAlerts = false;

// 2. INICIALIZAÇÃO NO CARREGAMENTO DA PÁGINA
document.addEventListener("DOMContentLoaded", () => {
    // Inicializar Tema
    initTheme();

    // Inicializar Sidebar Retrátil
    initSidebar();

    // Inicializar SPA
    switchView('dashboard');
    
    // Configurar listeners de data no filtro de notas
    const enableDateFilter = document.getElementById("filter-notas-enable-data");
    if (enableDateFilter) {
        enableDateFilter.addEventListener("change", (e) => {
            const dataFields = document.getElementById("filter-notas-data-fields");
            if (e.target.checked) {
                dataFields.classList.remove("hidden");
            } else {
                dataFields.classList.add("hidden");
            }
        });
    }

    // Configurar listener para o drag-and-drop de importação de arquivos
    const importFileInput = document.getElementById("dl-import-file-input");
    if (importFileInput) {
        importFileInput.addEventListener("change", (e) => {
            const countDiv = document.getElementById("dl-import-selected-count");
            if (e.target.files.length > 0) {
                countDiv.innerText = `📂 ${e.target.files.length} arquivo(s) selecionado(s)`;
                countDiv.classList.remove("hidden");
            } else {
                countDiv.classList.add("hidden");
            }
        });
    }

    // Preencher datas padrão (mês atual) — usar componentes locais para
    // evitar o deslocamento de fuso que toISOString() (UTC) pode causar
    const today = new Date();
    const firstDay = toLocalYMD(new Date(today.getFullYear(), today.getMonth(), 1));
    const lastDay = toLocalYMD(today);
    
    if (document.getElementById("dl-date-inicio")) document.getElementById("dl-date-inicio").value = firstDay;
    if (document.getElementById("dl-date-fim")) document.getElementById("dl-date-fim").value = lastDay;
    if (document.getElementById("filter-notas-data-inicio")) document.getElementById("filter-notas-data-inicio").value = firstDay;
    if (document.getElementById("filter-notas-data-fim")) document.getElementById("filter-notas-data-fim").value = lastDay;

    // Carregar dados iniciais das empresas do backend
    loadEmpresas();

    // Verificar se a última atualização do sistema aplicou tudo corretamente
    verificarResultadoAtualizacao();
});

// 3. ROTEADOR DE TELAS DA SPA (CLIENT-SIDE ROUTING)
function switchView(viewId) {
    AppState.currentView = viewId;

    // Ocultar todas as abas
    document.querySelectorAll(".spa-view").forEach(view => {
        view.classList.remove("active");
        view.classList.add("hidden");
    });

    // Exibir aba ativa
    const targetView = document.getElementById(`view-${viewId}`);
    if (targetView) {
        targetView.classList.remove("hidden");
        void targetView.offsetWidth; // Forçar reflow para animação
        targetView.classList.add("active");
    }

    // Atualizar menu lateral (Desktop)
    document.querySelectorAll("#desktop-nav .nav-item").forEach(item => {
        item.classList.remove("active");
    });
    const activeNav = document.getElementById(`nav-${viewId}`);
    if (activeNav) activeNav.classList.add("active");

    // Atualizar menu inferior (Mobile)
    document.querySelectorAll(".mobile-nav-item").forEach(item => {
        item.classList.remove("active");
    });
    const activeMobNav = document.getElementById(`mob-nav-${viewId}`);
    if (activeMobNav) activeMobNav.classList.add("active");

    // Atualizar título no TopAppBar
    const viewTitles = {
        'dashboard': 'Painel de Controle',
        'empresas': 'Gestão de Empresas',
        'downloads': 'Download XML NFSe',
        'notas': 'Notas Fiscais Catalogadas',
        'faturamento': 'Apuração de Faturamento',
        'agendamentos': 'Automação do Agendador',
        'config': 'Configuração & Backups'
    };
    const titleText = viewTitles[viewId] || 'NFS-e Portal';
    document.getElementById("current-view-title").innerHTML = `
        <span class="material-symbols-outlined text-primary">${getIconForView(viewId)}</span>
        <span>${titleText}</span>
    `;

    // Fechar menu mobile se aberto
    const sidebar = document.querySelector("aside");
    if (sidebar && !sidebar.classList.contains("hidden") && window.innerWidth < 768) {
        sidebar.classList.add("hidden");
    }

    // Carregar/atualizar dados da aba
    triggerViewLoad(viewId);
}

function getIconForView(viewId) {
    const icons = {
        'dashboard': 'dashboard',
        'empresas': 'business',
        'downloads': 'cloud_download',
        'notas': 'receipt_long',
        'faturamento': 'payments',
        'agendamentos': 'alarm',
        'config': 'settings_backup_restore'
    };
    return icons[viewId] || 'settings';
}

function toggleMobileMenu() {
    const sidebar = document.querySelector("aside");
    if (sidebar) {
        sidebar.classList.toggle("hidden");
    }
}

// 3.4. CONTROLE DA SIDEBAR RETRÁTIL (COLLAPSIBLE SIDEBAR)
function initSidebar() {
    const isCollapsed = localStorage.getItem("sidebarCollapsed") === "true";
    const body = document.body;
    const btn = document.getElementById("btn-toggle-sidebar");
    
    if (isCollapsed) {
        body.classList.add("sidebar-collapsed");
        if (btn) {
            btn.innerHTML = `<span class="material-symbols-outlined text-[20px]">left_panel_open</span>`;
            btn.setAttribute("title", "Abrir barra lateral");
        }
    } else {
        body.classList.remove("sidebar-collapsed");
        if (btn) {
            btn.innerHTML = `<span class="material-symbols-outlined text-[20px]">left_panel_close</span>`;
            btn.setAttribute("title", "Fechar barra lateral");
        }
    }
}

function toggleSidebar() {
    const body = document.body;
    const isCollapsed = body.classList.toggle("sidebar-collapsed");
    localStorage.setItem("sidebarCollapsed", isCollapsed);
    
    const btn = document.getElementById("btn-toggle-sidebar");
    if (btn) {
        if (isCollapsed) {
            btn.innerHTML = `<span class="material-symbols-outlined text-[20px]">left_panel_open</span>`;
            btn.setAttribute("title", "Abrir barra lateral");
        } else {
            btn.innerHTML = `<span class="material-symbols-outlined text-[20px]">left_panel_close</span>`;
            btn.setAttribute("title", "Fechar barra lateral");
        }
    }
}


// 3.5. CONTROLE DE TEMA CLARO/ESCURO (MATERIAL DESIGN 3)
function initTheme() {
    const savedTheme = localStorage.getItem("theme") || "light";
    if (savedTheme === "dark") {
        document.documentElement.classList.remove("light");
        document.documentElement.classList.add("dark");
        const themeIcon = document.getElementById("theme-icon");
        if (themeIcon) themeIcon.innerText = "light_mode";
    } else {
        document.documentElement.classList.remove("dark");
        document.documentElement.classList.add("light");
        const themeIcon = document.getElementById("theme-icon");
        if (themeIcon) themeIcon.innerText = "dark_mode";
    }
}

function toggleTheme() {
    const isDark = document.documentElement.classList.contains("dark");
    const themeIcon = document.getElementById("theme-icon");
    
    if (isDark) {
        document.documentElement.classList.remove("dark");
        document.documentElement.classList.add("light");
        localStorage.setItem("theme", "light");
        if (themeIcon) themeIcon.innerText = "dark_mode";
        showToast("Tema Claro ativado!", "info");
    } else {
        document.documentElement.classList.remove("light");
        document.documentElement.classList.add("dark");
        localStorage.setItem("theme", "dark");
        if (themeIcon) themeIcon.innerText = "light_mode";
        showToast("Tema Escuro ativado!", "info");
    }

    // Re-renderiza o gráfico com a paleta do tema atual
    if (AppState.faturamentoChart) {
        renderFaturamentoChart(AppState.faturamentoChartData || []);
    }
}

// Dispara o carregamento sob demanda ao trocar de tela
function triggerViewLoad(viewId) {
    switch (viewId) {
        case 'dashboard':
            refreshDashboard();
            break;
        case 'empresas':
            loadEmpresas();
            break;
        case 'downloads':
            populateCompanyDropdowns();
            break;
        case 'notas':
            populateCompanyDropdowns();
            refreshNotasTable(1);
            break;
        case 'faturamento':
            // Resetar visualização de relatório e preencher selectors
            populateCompanyDropdowns();
            document.getElementById("faturamento-report-container").classList.add("hidden");
            break;
        case 'agendamentos':
            refreshAgendamentos();
            break;
        case 'config':
            populateCompanyDropdowns();
            refreshConfig();
            break;
    }
}

// 4. SISTEMA DE TOAST NOTIFICATIONS (ALERTAS FLUTUANTES)
function showToast(mensagem, tipo = 'info', duracao = 4000) {
    const container = document.getElementById("toast-container");
    if (!container) return;

    const toast = document.createElement("div");
    toast.className = `toast toast-${tipo}`;

    const icons = {
        'success': 'check_circle',
        'error': 'error',
        'warning': 'warning',
        'info': 'info'
    };
    const icon = icons[tipo] || 'info';

    toast.innerHTML = `
        <span class="material-symbols-outlined icon">${icon}</span>
        <div class="flex-1 text-xs font-semibold text-on-surface">${mensagem}</div>
        <button class="p-1 hover:bg-surface-container rounded-full text-on-surface-variant transition-colors" onclick="this.parentElement.remove()">
            <span class="material-symbols-outlined text-[16px]">close</span>
        </button>
    `;

    container.appendChild(toast);

    // Auto-remove
    setTimeout(() => {
        toast.classList.add("removing");
        setTimeout(() => toast.remove(), 300);
    }, duracao);
}

// 5. AUXILIARES DE FORMATAÇÃO (BR/PT)
function formatCNPJ(cnpj) {
    if (!cnpj) return "";
    const clean = cnpj.replace(/\D/g, "");
    if (clean.length !== 14) return cnpj;
    return `${clean.substring(0, 2)}.${clean.substring(2, 5)}.${clean.substring(5, 8)}/${clean.substring(8, 12)}-${clean.substring(12, 14)}`;
}

function formatCurrency(valor) {
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(valor || 0);
}

// Formata um objeto Date usando os componentes LOCAIS (AAAA-MM-DD),
// sem passar por toISOString() — que converte para UTC e pode deslocar o dia.
function toLocalYMD(date) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
}

function formatShortDate(dateStr) {
    if (!dateStr) return "N/A";
    try {
        // Datas puras AAAA-MM-DD do backend: formatar direto, sem new Date(),
        // que as interpreta como meia-noite UTC e mostra -1 dia no Brasil.
        const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(dateStr);
        if (m) return `${m[3]}/${m[2]}/${m[1]}`;
        const d = new Date(dateStr);           // fallback para outros formatos
        if (isNaN(d.getTime())) return dateStr;
        return d.toLocaleDateString('pt-BR');
    } catch {
        return dateStr;
    }
}

// 6. GESTÃO DE EMPRESAS (LOAD, ADD, EDIT, DELETE)
async function loadEmpresas() {
    try {
        const response = await fetch("/api/empresas");
        if (!response.ok) throw new Error("Erro ao buscar empresas");
        
        const data = await response.json();
        AppState.empresas = data;
        
        // Atualizar alertas de certificados expirados
        checkCertificatesAlerts();

        // Renderizar cards de empresas se a view atual for a de empresas
        if (AppState.currentView === 'empresas') {
            renderEmpresasCards();
        }
        
        // Atualizar selectors em todas as views
        populateCompanyDropdowns();
        
    } catch (e) {
        showToast(`Falha ao conectar com o backend: ${e.message}`, 'error');
    }
}

function checkCertificatesAlerts() {
    const alertsContainer = document.getElementById("empresas-alerts-container");
    const notificationBadge = document.getElementById("notification-badge");
    
    if (!alertsContainer) return;
    alertsContainer.innerHTML = "";
    let alertCount = 0;

    AppState.empresas.forEach(emp => {
        const days = emp.certificado_dias_restantes;
        
        if (days >= 0 && days <= 30) {
            alertCount++;
            const div = document.createElement("div");
            div.className = `p-4 border rounded-xl flex items-start gap-3 shadow-xs ${days <= 7 ? 'bg-error/10 border-error/30 text-error' : 'bg-warning/10 border-warning/30 text-on-surface'}`;
            div.innerHTML = `
                <span class="material-symbols-outlined text-2xl ${days <= 7 ? 'text-error' : 'text-warning'}">warning</span>
                <div class="flex-1">
                    <h4 class="text-xs font-bold">Certificado Próximo do Vencimento!</h4>
                    <p class="text-[10px] opacity-90 mt-0.5">A empresa <strong>${emp.razao_social}</strong> está com o certificado vencendo em <strong>${days} dias</strong> (${emp.certificado_vencimento}). Por favor, atualize o arquivo .pfx.</p>
                </div>
            `;
            alertsContainer.appendChild(div);
        } else if (days < 0) {
            alertCount++;
            const div = document.createElement("div");
            div.className = "p-4 bg-error/10 border border-error/30 text-error rounded-xl flex items-start gap-3 shadow-xs";
            div.innerHTML = `
                <span class="material-symbols-outlined text-2xl text-error">report</span>
                <div class="flex-1">
                    <h4 class="text-xs font-bold">Certificado Vencido ou Inválido!</h4>
                    <p class="text-[10px] opacity-90 mt-0.5">A empresa <strong>${emp.razao_social}</strong> está com certificado digital bloqueado ou vencido. Atualize a chave de segurança para continuar sincronizando notas.</p>
                </div>
            `;
            alertsContainer.appendChild(div);
        }
    });

    if (alertCount > 0) {
        alertsContainer.classList.remove("hidden");
        if (notificationBadge) notificationBadge.classList.remove("hidden");
    } else {
        alertsContainer.classList.add("hidden");
        if (notificationBadge) notificationBadge.classList.add("hidden");
    }

    // Exibir avisos automáticos do tipo Toast e na central de notificações na inicialização do sistema (Boot)
    if (!hasShownBootAlerts) {
        AppState.empresas.forEach(emp => {
            const days = emp.certificado_dias_restantes;
            if (days >= 0 && days <= 30) {
                const msg = `O certificado digital da empresa <strong>${emp.razao_social}</strong> vence em ${days} dias (${emp.certificado_vencimento})!`;
                showToast(msg, 'warning', 6000);
                addNotification(msg, 'warning');
            } else if (days < 0) {
                const msg = `O certificado digital da empresa <strong>${emp.razao_social}</strong> está expirado (${emp.certificado_vencimento})!`;
                showToast(msg, 'error', 7000);
                addNotification(msg, 'error');
            }
        });
        hasShownBootAlerts = true;
    }
}

function renderEmpresasCards() {
    // Renderiza as empresas em LINHAS (tabela), no estilo do Integra Contador.
    const tbody = document.getElementById("empresas-table-body");
    if (!tbody) return;

    if (AppState.empresas.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="6" class="text-center py-16 text-on-surface-variant">
                    <span class="material-symbols-outlined text-4xl text-primary opacity-60">business_center</span>
                    <p class="font-bold text-sm mt-3 text-on-surface">Nenhuma empresa cadastrada</p>
                    <p class="text-xs mt-1">Cadastre sua primeira empresa emissora ou tomadora para iniciar a gestão.</p>
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = "";
    AppState.empresas.forEach(emp => {
        const days = emp.certificado_dias_restantes;
        let badgeColor = "bg-success/10 text-success border-success/30";
        let statusText = `${days} dias`;
        let certIcon = "verified";

        if (days >= 0 && days <= 30) {
            badgeColor = "bg-warning/10 text-warning border-warning/30";
            statusText = `Vence em ${days} dias`;
            certIcon = "warning";
        } else if (days < 0) {
            badgeColor = "bg-error/10 text-error border-error/30";
            statusText = "Expirado";
            certIcon = "error";
        }

        const tr = document.createElement("tr");
        tr.className = "hover:bg-surface-container-low transition-colors";
        tr.innerHTML = `
            <td class="px-5 py-3">
                <div class="font-semibold text-on-surface line-clamp-1">${emp.razao_social}</div>
                <div class="text-[11px] text-on-surface-variant line-clamp-1">${emp.nome_fantasia || "Sem nome fantasia"}</div>
            </td>
            <td class="px-5 py-3 font-mono text-on-surface-variant whitespace-nowrap">${emp.cnpj_formatado}</td>
            <td class="px-5 py-3">
                <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold border ${badgeColor}">
                    <span class="material-symbols-outlined text-[13px]">${certIcon}</span>${statusText}
                </span>
                <div class="text-[10px] text-on-surface-variant mt-0.5">${emp.certificado_vencimento || ""}</div>
            </td>
            <td class="px-5 py-3 text-right font-mono font-bold text-primary whitespace-nowrap">${emp.ultimo_nsu || 0}</td>
            <td class="px-5 py-3 text-center">
                <span class="inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-bold ${emp.ativo ? 'bg-primary/10 text-primary' : 'bg-secondary-container text-on-secondary-container'}">
                    ${emp.ativo ? 'ATIVA' : 'INATIVA'}
                </span>
            </td>
            <td class="px-5 py-3">
                <div class="flex items-center justify-center gap-1.5">
                    <button onclick="openCadastroModal(${emp.id})" class="h-8 px-3 border border-border rounded-lg text-[11px] font-semibold flex items-center gap-1 hover:bg-surface-container transition-all" title="Editar empresa">
                        <span class="material-symbols-outlined text-[15px]">edit</span> Editar
                    </button>
                    <button onclick="excluirEmpresa(${emp.id})" class="h-8 w-8 bg-error/10 text-error rounded-lg flex items-center justify-center hover:bg-error/20 transition-all" title="Excluir empresa">
                        <span class="material-symbols-outlined text-[16px]">delete</span>
                    </button>
                </div>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

function populateCompanyDropdowns() {
    const dropdownIds = [
        "dl-empresa-select", 
        "dl-empresa-import-select", 
        "filter-notas-empresa", 
        "test-empresa-select"
    ];

    dropdownIds.forEach(id => {
        const select = document.getElementById(id);
        if (!select) return;
        
        // Se for o filtro da aba notas, mantém a opção global
        const keepsAllOption = id === "filter-notas-empresa";
        select.innerHTML = keepsAllOption ? '<option value="todas">Todas as Empresas</option>' : '';
        
        if (AppState.empresas.length === 0) {
            if (!keepsAllOption) select.innerHTML = '<option value="">Nenhuma empresa cadastrada</option>';
            return;
        }

        AppState.empresas.forEach(emp => {
            const option = document.createElement("option");
            option.value = emp.id;
            option.text = `${emp.razao_social} (${emp.cnpj_formatado})`;
            select.appendChild(option);
        });
    });
}

function openCadastroModal(empresaId = null) {
    const modal = document.getElementById("cadastro-modal");
    const form = document.getElementById("cadastro-form");
    const idInput = document.getElementById("cadastro-empresa-id");
    const cnpjInput = document.getElementById("cadastro-cnpj");
    const titleText = document.getElementById("cadastro-modal-title");
    const editMsg = document.getElementById("cadastro-cert-edit-msg");
    const labelCert = document.getElementById("label-cadastro-certificado");

    if (!modal || !form) return;

    form.reset();

    if (empresaId) {
        // Modo Edição
        const emp = AppState.empresas.find(e => e.id === empresaId);
        if (!emp) return;

        idInput.value = emp.id;
        cnpjInput.value = emp.cnpj;
        cnpjInput.setAttribute("disabled", "true"); // Bloquear edição do CNPJ
        document.getElementById("cadastro-razao-social").value = emp.razao_social;
        document.getElementById("cadastro-nome-fantasia").value = emp.nome_fantasia || "";
        document.getElementById("cadastro-ativo").checked = emp.ativo;
        document.getElementById("cadastro-certificado").removeAttribute("required");

        titleText.innerHTML = `<span class="material-symbols-outlined">edit</span> <span>Editar Empresa</span>`;
        editMsg.innerText = "Deixe em branco para manter o certificado PFX atual.";
        labelCert.innerText = "Substituir Certificado A1 (.pfx)";
    } else {
        // Modo Novo Cadastro
        idInput.value = "";
        cnpjInput.removeAttribute("disabled");
        document.getElementById("cadastro-certificado").setAttribute("required", "true");

        titleText.innerHTML = `<span class="material-symbols-outlined">add_business</span> <span>Nova Empresa</span>`;
        editMsg.innerText = "Necessário fazer upload do arquivo de chaves (.pfx).";
        labelCert.innerText = "Certificado Digital (.pfx A1)";
    }

    modal.classList.remove("hidden");
    void modal.offsetWidth;
    modal.classList.add("active");
}

function closeCadastroModal() {
    const modal = document.getElementById("cadastro-modal");
    if (modal) {
        modal.classList.remove("active");
        setTimeout(() => modal.classList.add("hidden"), 250);
    }
}

async function submitCadastroForm(event) {
    event.preventDefault();
    
    const id = document.getElementById("cadastro-empresa-id").value;
    const form = document.getElementById("cadastro-form");
    const formData = new FormData(form);
    
    // Forçar booleano de ativação
    const ativoVal = document.getElementById("cadastro-ativo").checked;
    formData.set("ativo", ativoVal ? "true" : "false");

    const isEdit = id !== "";
    const url = isEdit ? `/api/empresas/${id}` : "/api/empresas";
    const method = isEdit ? "PUT" : "POST";

    // Remover certificado de FormData na edição se não enviado
    const certInput = document.getElementById("cadastro-certificado");
    if (isEdit && certInput.files.length === 0) {
        formData.delete("certificado");
    }

    try {
        showToast("Enviando credenciais e validando certificado...", "info");
        const response = await fetch(url, {
            method: method,
            body: formData
        });

        const resData = await response.json();

        if (!response.ok) {
            throw new Error(resData.detail || "Falha na validação do certificado.");
        }

        if (resData.success) {
            showToast(isEdit ? "Empresa atualizada com sucesso!" : "Empresa cadastrada e validada!", "success");
            closeCadastroModal();
            loadEmpresas();
        } else {
            throw new Error(resData.error || "Falha inexplicada.");
        }
    } catch (e) {
        showToast(`Erro de cadastro: ${e.message}`, "error");
    }
}

async function excluirEmpresa(id) {
    const emp = AppState.empresas.find(e => e.id === id);
    if (!emp) return;

    if (!confirm(`Deseja realmente EXCLUIR a empresa "${emp.razao_social}"?\nEsta ação irá remover todos os XMLs e registros vinculados no banco de dados.`)) {
        return;
    }

    try {
        const response = await fetch(`/api/empresas/${id}`, { method: "DELETE" });
        const res = await response.json();
        
        if (response.ok && res.success) {
            showToast("Empresa removida com sucesso!", "success");
            loadEmpresas();
        } else {
            throw new Error(res.detail || "Erro ao deletar.");
        }
    } catch (e) {
        showToast(`Erro na exclusão: ${e.message}`, "error");
    }
}

// 7. MOTOR DE DOWNLOADS ASSÍNCRONOS E LOG POLLING
let activeDownloadMode = 'individual';
function setDownloadMode(mode) {
    activeDownloadMode = mode;
    
    const btnInd = document.getElementById("btn-mode-ind");
    const btnLote = document.getElementById("btn-mode-lote");
    const btnImp = document.getElementById("btn-mode-imp");

    const indFields = document.getElementById("dl-individual-fields");
    const loteFields = document.getElementById("dl-lote-fields");
    const filtersFields = document.getElementById("dl-filters-fields");
    const importFields = document.getElementById("dl-import-fields");

    const btnExecutar = document.getElementById("btn-dl-executar");

    // Reset styles de botões
    [btnInd, btnLote, btnImp].forEach(btn => {
        if (btn) {
            btn.className = "flex-1 py-2 text-xs font-semibold rounded-lg text-on-surface-variant hover:bg-surface-container-high transition-all";
        }
    });

    // Ocultar formulários
    [indFields, loteFields, filtersFields, importFields].forEach(el => {
        if (el) el.classList.add("hidden");
    });

    if (mode === 'individual') {
        if (btnInd) btnInd.className = "flex-1 py-2 text-xs font-semibold rounded-lg bg-surface text-primary shadow-sm transition-all";
        if (indFields) indFields.classList.remove("hidden");
        if (filtersFields) filtersFields.classList.remove("hidden");
        if (btnExecutar) {
            btnExecutar.innerHTML = `<span class="material-symbols-outlined text-[20px]">search</span> Buscar NFS-e Nacional`;
            btnExecutar.className = "w-full h-12 bg-primary text-on-primary rounded-full font-semibold text-label-lg flex items-center justify-center gap-2 hover:opacity-90 active:scale-95 shadow-md transition-all mt-6";
        }
    } else if (mode === 'lote') {
        if (btnLote) btnLote.className = "flex-1 py-2 text-xs font-semibold rounded-lg bg-surface text-primary shadow-sm transition-all";
        if (loteFields) loteFields.classList.remove("hidden");
        if (filtersFields) filtersFields.classList.remove("hidden");
        if (btnExecutar) {
            btnExecutar.innerHTML = `<span class="material-symbols-outlined text-[20px]">sync_alt</span> Sincronizar Tudo em Lote`;
            btnExecutar.className = "w-full h-12 bg-primary text-on-primary rounded-full font-semibold text-label-lg flex items-center justify-center gap-2 hover:opacity-90 active:scale-95 shadow-md transition-all mt-6";
        }
    } else if (mode === 'import') {
        if (btnImp) btnImp.className = "flex-1 py-2 text-xs font-semibold rounded-lg bg-surface text-primary shadow-sm transition-all";
        if (importFields) importFields.classList.remove("hidden");
        if (btnExecutar) {
            btnExecutar.innerHTML = `<span class="material-symbols-outlined text-[20px]">upload_file</span> Processar Importação Manual`;
            btnExecutar.className = "w-full h-12 bg-success text-on-primary rounded-full font-semibold text-label-lg flex items-center justify-center gap-2 hover:opacity-90 active:scale-95 shadow-md transition-all mt-6";
        }
    }
}

async function triggerDownloadAction() {
    if (activeDownloadMode === 'import') {
        triggerImportManual();
        return;
    }

    const tipo = document.getElementById("dl-tipo-select").value;
    const tipoPeriodo = document.getElementById("dl-periodo-select").value;
    const dataInicio = document.getElementById("dl-date-inicio").value;
    const dataFim = document.getElementById("dl-date-fim").value;

    if (!dataInicio || !dataFim) {
        showToast("Selecione um intervalo de datas válido", "warning");
        return;
    }

    const form = new FormData();
    form.append("tipo", tipo);
    form.append("tipo_periodo", tipoPeriodo);
    form.append("data_inicio", dataInicio);
    form.append("data_fim", dataFim);

    let url = "";

    if (activeDownloadMode === 'individual') {
        const empId = document.getElementById("dl-empresa-select").value;
        if (!empId) {
            showToast("Selecione a empresa cadastrada ativa", "warning");
            return;
        }
        const reescanear = document.getElementById("dl-reescanear").checked;
        form.append("empresa_id", empId);
        form.append("reescanear", reescanear ? "true" : "false");
        url = "/api/downloads/iniciar";
    } else {
        url = "/api/downloads/lote";
    }

    try {
        const response = await fetch(url, { method: "POST", body: form });
        const res = await response.json();

        if (!response.ok) throw new Error(res.detail || "Falha ao disparar tarefa.");

        // Limpar logs e barra de progresso no terminal
        const terminal = document.getElementById("dl-terminal");
        if (terminal) terminal.innerHTML = `<p class="text-neutral-500">// Operação iniciada. Conectando à API da Receita Federal...</p>`;
        AppState.lastPolledLogIndex = 0;
        
        // Ocultar estatísticas antigas
        document.getElementById("dl-stats-container").classList.add("hidden");
        
        // Bloquear botão
        const btnExecutar = document.getElementById("btn-dl-executar");
        if (btnExecutar) btnExecutar.setAttribute("disabled", "true");

        // Iniciar polling
        startLogPolling(res.download_id);

    } catch (e) {
        showToast(`Erro ao iniciar download: ${e.message}`, "error");
    }
}

function startLogPolling(downloadId) {
    if (AppState.downloadPollingInterval) clearInterval(AppState.downloadPollingInterval);
    
    const terminal = document.getElementById("dl-terminal");
    const progressBar = document.getElementById("dl-progress-bar");
    const percentage = document.getElementById("dl-progress-percentage");
    const msg = document.getElementById("dl-progress-msg");
    const btnExecutar = document.getElementById("btn-dl-executar");

    AppState.downloadPollingInterval = setInterval(async () => {
        try {
            const response = await fetch(`/api/downloads/status/${downloadId}`);
            if (!response.ok) return;

            const data = await response.json();

            // Atualizar progresso e status
            const currentPct = Math.round(data.progresso * 100);
            if (progressBar) progressBar.style.width = `${currentPct}%`;
            if (percentage) percentage.innerText = `Progresso: ${currentPct}%`;
            if (msg) msg.innerText = data.mensagem || "Processando...";

            // Injetar logs novos na tela
            if (data.logs && data.logs.length > AppState.lastPolledLogIndex) {
                for (let i = AppState.lastPolledLogIndex; i < data.logs.length; i++) {
                    const rawLog = data.logs[i];
                    const div = document.createElement("div");
                    div.className = "log-line";
                    
                    // Detecção de tipo de log e colorização
                    if (rawLog.includes("Erro") || rawLog.includes("❌")) {
                        div.innerHTML = `<span class="log-error">${rawLog}</span>`;
                    } else if (rawLog.includes("sucesso") || rawLog.includes("concluído") || rawLog.includes("▶️") || rawLog.includes("Processando documento")) {
                        div.innerHTML = `<span class="log-success">${rawLog}</span>`;
                    } else if (rawLog.includes("Buscando") || rawLog.includes("Descobrindo") || rawLog.includes("Consultando")) {
                        div.innerHTML = `<span class="log-info">${rawLog}</span>`;
                    } else if (rawLog.includes("Aviso") || rawLog.includes("⚠️") || rawLog.includes("Pendente")) {
                        div.innerHTML = `<span class="log-warning">${rawLog}</span>`;
                    } else if (rawLog.includes("Zerar NSU") || rawLog.includes("Sincronização")) {
                        div.innerHTML = `<span class="log-system">${rawLog}</span>`;
                    } else {
                        div.innerHTML = `<span class="log-debug">${rawLog}</span>`;
                    }
                    
                    if (terminal) {
                        terminal.appendChild(div);
                        terminal.scrollTop = terminal.scrollHeight;
                    }
                }
                AppState.lastPolledLogIndex = data.logs.length;
            }

            // Validar encerramento
            if (data.status === 'concluido' || data.status === 'erro') {
                clearInterval(AppState.downloadPollingInterval);
                if (btnExecutar) btnExecutar.removeAttribute("disabled");

                if (data.status === 'concluido') {
                    const successMsg = data.mensagem || "Sincronização finalizada com sucesso!";
                    showToast(successMsg, "success");
                    addNotification(successMsg, "success");
                    
                    // Exibir estatísticas
                    const statsBox = document.getElementById("dl-stats-container");
                    if (statsBox) {
                        // Trata estatísticas em lote ou individual
                        const novas = data.stats.total_novas !== undefined ? data.stats.total_novas : (data.stats.novas !== undefined ? data.stats.novas : 0);
                        const erros = data.stats.total_erros !== undefined ? data.stats.total_erros : (data.stats.erros !== undefined ? data.stats.erros : 0);
                        const encontradas = data.stats.total_encontradas !== undefined ? data.stats.total_encontradas : novas;
                        const duplicadas = data.stats.duplicadas !== undefined ? data.stats.duplicadas : 0;

                        document.getElementById("dl-stat-encontradas").innerText = encontradas;
                        document.getElementById("dl-stat-novas").innerText = novas;
                        document.getElementById("dl-stat-duplicadas").innerText = duplicadas;
                        document.getElementById("dl-stat-erros").innerText = erros;
                        
                        statsBox.classList.remove("hidden");
                    }
                } else {
                    const errorMsg = data.mensagem || "Erro na execução da busca.";
                    showToast(errorMsg, "error");
                    addNotification(errorMsg, "error");
                }

                // Forçar atualização em segundo plano
                refreshDashboard();
            }

        } catch (e) {
            console.error("Erro no polling de logs", e);
        }
    }, 500);
}

async function triggerImportManual() {
    const empId = document.getElementById("dl-empresa-import-select").value;
    const fileInput = document.getElementById("dl-import-file-input");

    if (!empId) {
        showToast("Selecione a empresa de destino para os XMLs", "warning");
        return;
    }

    if (fileInput.files.length === 0) {
        showToast("Selecione pelo menos um arquivo XML para upload", "warning");
        return;
    }

    const form = new FormData();
    form.append("empresa_id", empId);
    for (let i = 0; i < fileInput.files.length; i++) {
        form.append("xml_files", fileInput.files[i]);
    }

    const btnExecutar = document.getElementById("btn-dl-executar");

    try {
        showToast("Processando arquivos XML...", "info");
        if (btnExecutar) btnExecutar.setAttribute("disabled", "true");

        const response = await fetch("/api/downloads/importar", {
            method: "POST",
            body: form
        });

        const res = await response.json();
        
        if (!response.ok) throw new Error(res.detail || "Erro no processamento.");

        const msg = `Importação manual concluída: ${res.importadas} novas, ${res.duplicadas} duplicadas, ${res.erros} erros.`;
        showToast(msg, "success");
        addNotification(msg, "success");
        
        // Exibir na console de logs os detalhes
        const terminal = document.getElementById("dl-terminal");
        if (terminal) {
            terminal.innerHTML = `<p class="text-neutral-500">// Relatório de Importação Manual:</p>`;
            res.detalhes.forEach(det => {
                const div = document.createElement("div");
                div.className = "log-line log-info";
                div.innerText = det;
                terminal.appendChild(div);
            });
        }

        fileInput.value = "";
        document.getElementById("dl-import-selected-count").classList.add("hidden");

    } catch (e) {
        showToast(`Erro na importação: ${e.message}`, "error");
    } finally {
        if (btnExecutar) btnExecutar.removeAttribute("disabled");
    }
}

// 8. ABA DE NOTAS FISCAIS CATALOGADAS
function limparFiltrosColuna() {
    AppState.columnFilters = {
        numero: '',
        numero_dps: '',
        serie: '',
        data_emissao: '',
        prestador_nome: '',
        tomador_nome: '',
        valor_servicos: '',
        status: ''
    };
    AppState.sortColumn = null;
    AppState.sortOrder = 'asc';
    
    // Limpar os campos no DOM
    const inputs = document.querySelectorAll('#view-notas thead input');
    inputs.forEach(input => input.value = '');
    const selects = document.querySelectorAll('#view-notas thead select');
    selects.forEach(select => select.value = '');
    
    updateSortIcons();
}

function updateSortIcons() {
    const columns = ['numero', 'numero_dps', 'serie', 'data_emissao', 'prestador_nome', 'tomador_nome', 'valor_servicos', 'status'];
    columns.forEach(col => {
        const span = document.getElementById(`sort-icon-${col}`);
        if (!span) return;
        if (AppState.sortColumn === col) {
            span.innerHTML = AppState.sortOrder === 'asc' ? ' &uarr;' : ' &darr;';
            span.className = "text-[12px] text-primary font-bold ml-1";
        } else {
            span.innerHTML = '';
            span.className = "text-[10px]";
        }
    });
}

function filtrarNotasColuna(coluna, valor) {
    AppState.columnFilters[coluna] = valor.trim().toLowerCase();
    AppState.notesPage = 1; // Volta para a primeira página
    renderNotasTable();
}

function ordenarNotasTable(coluna) {
    if (AppState.sortColumn === coluna) {
        if (AppState.sortOrder === 'asc') {
            AppState.sortOrder = 'desc';
        } else if (AppState.sortOrder === 'desc') {
            AppState.sortColumn = null;
            AppState.sortOrder = 'asc';
        }
    } else {
        AppState.sortColumn = coluna;
        AppState.sortOrder = 'asc';
    }
    
    updateSortIcons();
    renderNotasTable();
}

async function refreshNotasTable(page = 1) {
    AppState.notesPage = page;
    AppState.selectedNotas.clear();
    updateSelectedNotasCount();

    if (page === 1) {
        limparFiltrosColuna();
    }

    const textBusca = document.getElementById("filter-notas-busca").value;
    const empId = document.getElementById("filter-notas-empresa").value;
    const tipo = document.getElementById("filter-notas-tipo").value;
    const enableDate = document.getElementById("filter-notas-enable-data").checked;

    // Buscamos um limite alto para fazermos ordenação e filtros locais ultra-rápidos
    let url = `/api/notas?page=1&limit=100000`;

    if (textBusca) url += `&texto_busca=${encodeURIComponent(textBusca)}`;
    if (empId && empId !== 'todas') url += `&empresa_id=${empId}`;
    if (tipo && tipo !== 'todas') url += `&tipo=${tipo}`;

    if (enableDate) {
        const campoData = document.querySelector('input[name="filter-campo-data"]:checked').value;
        const datIni = document.getElementById("filter-notas-data-inicio").value;
        const datFim = document.getElementById("filter-notas-data-fim").value;
        
        url += `&campo_data=${campoData}`;
        if (datIni) url += `&data_inicio=${datIni}`;
        if (datFim) url += `&data_fim=${datFim}`;
    }

    const tbody = document.getElementById("notas-table-body");
    if (tbody) tbody.innerHTML = `<tr><td colspan="10" class="text-center py-20 text-on-surface-variant"><span class="animate-pulse flex items-center justify-center gap-1.5"><span class="material-symbols-outlined text-[20px] animate-spin">sync</span> Carregando base de dados...</span></td></tr>`;

    try {
        const response = await fetch(url);
        if (!response.ok) throw new Error("Erro ao listar notas.");

        const data = await response.json();
        AppState.allNotas = data.notas || [];

        // 2. Banner de lacunas sequenciais (independente de filtros locais)
        const gapBanner = document.getElementById("notas-gap-banner");
        const gapMsg = document.getElementById("notas-gap-msg");
        if (gapBanner && gapMsg) {
            if (data.gaps && data.gaps.total_faltantes > 0) {
                gapMsg.innerHTML = `Foram detectados <strong>${data.gaps.total_faltantes} furos</strong> de numeração na sequência do contribuinte entre as notas <strong>#${data.gaps.primeiro}</strong> e <strong>#${data.gaps.ultimo}</strong>.<br>Números ausentes encontrados: <strong>${data.gaps.numeros.join(', ')}${data.gaps.total_faltantes > 15 ? '...' : ''}</strong>.`;
                gapBanner.classList.remove("hidden");
            } else {
                gapBanner.classList.add("hidden");
            }
        }

        // Renderiza a tabela com paginação e ordenação locais
        renderNotasTable();

        document.getElementById("notas-select-all").checked = false;

    } catch (e) {
        showToast(`Erro na listagem das notas: ${e.message}`, "error");
    }
}

// Busca ativa de notas faltantes: consulta a SEFIN Nacional pelas DPS
// ausentes na sequência de numeração e recupera as notas existentes
async function buscarNotasFaltantes() {
    const select = document.getElementById("filter-notas-empresa");
    const empresaId = select ? select.value : null;

    if (!empresaId || empresaId === "todas") {
        showToast("Selecione uma empresa específica no filtro para buscar faltantes.", "warning");
        return;
    }

    const btn = document.getElementById("btn-buscar-faltantes");
    const btnHtmlOriginal = btn ? btn.innerHTML : null;
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<span class="material-symbols-outlined text-[16px] animate-spin">sync</span> Consultando SEFIN...`;
    }

    try {
        const formData = new FormData();
        formData.append("empresa_id", empresaId);

        const response = await fetch("/api/notas/buscar-faltantes", {
            method: "POST",
            body: formData
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "Falha na busca ativa");

        if (data.recuperadas > 0) {
            showToast(`✅ ${data.recuperadas} nota(s) recuperada(s)! ${data.sem_nfse} lacuna(s) legítima(s) em ${data.consultadas} consulta(s).`, "success");
        } else if (data.consultadas > 0) {
            showToast(`Nenhuma nota recuperada: ${data.sem_nfse} de ${data.consultadas} lacuna(s) consultada(s) nunca viraram NFS-e.`, "info");
        } else {
            showToast("Nenhuma lacuna de numeração DPS para consultar.", "info");
        }

        if (data.erros > 0) {
            showToast(`${data.erros} consulta(s) com erro — veja os logs do servidor.`, "warning");
        }

        refreshNotasTable(1);
    } catch (e) {
        showToast(`Erro na busca ativa: ${e.message}`, "error");
    } finally {
        if (btn && btnHtmlOriginal) {
            btn.disabled = false;
            btn.innerHTML = btnHtmlOriginal;
        }
    }
}

function renderNotasTable() {
    let filtered = [...AppState.allNotas];

    // Aplicar filtros por coluna
    const filterKeys = Object.keys(AppState.columnFilters);
    filterKeys.forEach(col => {
        const val = AppState.columnFilters[col];
        if (!val) return;
        
        filtered = filtered.filter(nota => {
            if (col === 'numero') {
                return (nota.numero || '').toString().toLowerCase().includes(val);
            }
            if (col === 'numero_dps') {
                return (nota.numero_dps || '').toString().toLowerCase().includes(val);
            }
            if (col === 'serie') {
                return (nota.serie || '0').toString().toLowerCase().includes(val);
            }
            if (col === 'data_emissao') {
                const dateStr = formatShortDate(nota.data_emissao).toLowerCase();
                return dateStr.includes(val);
            }
            if (col === 'prestador_nome') {
                const prestador = `${nota.prestador_nome || ''} ${nota.prestador_cnpj_formatado || ''}`.toLowerCase();
                return prestador.includes(val);
            }
            if (col === 'tomador_nome') {
                const tomador = `${nota.tomador_nome || ''} ${nota.tomador_cnpj_formatado || ''}`.toLowerCase();
                return tomador.includes(val);
            }
            if (col === 'valor_servicos') {
                const valorStr = formatCurrency(nota.valor_servicos).toLowerCase();
                const rawVal = (nota.valor_servicos || 0).toString().toLowerCase();
                return valorStr.includes(val) || rawVal.includes(val);
            }
            if (col === 'status') {
                return (nota.status || '').toString().toLowerCase() === val; // correspondência exata para dropdown status
            }
            return false;
        });
    });

    // Aplicar ordenação por coluna
    if (AppState.sortColumn) {
        const col = AppState.sortColumn;
        const order = AppState.sortOrder === 'asc' ? 1 : -1;
        
        filtered.sort((a, b) => {
            let valA, valB;
            if (col === 'numero') {
                valA = parseInt(a.numero) || 0;
                valB = parseInt(b.numero) || 0;
            } else if (col === 'numero_dps') {
                valA = parseInt(a.numero_dps) || 0;
                valB = parseInt(b.numero_dps) || 0;
            } else if (col === 'serie') {
                valA = parseInt(a.serie) || 0;
                valB = parseInt(b.serie) || 0;
            } else if (col === 'data_emissao') {
                valA = new Date(a.data_emissao || 0).getTime();
                valB = new Date(b.data_emissao || 0).getTime();
            } else if (col === 'prestador_nome') {
                valA = (a.prestador_nome || '').toLowerCase();
                valB = (b.prestador_nome || '').toLowerCase();
            } else if (col === 'tomador_nome') {
                valA = (a.tomador_nome || '').toLowerCase();
                valB = (b.tomador_nome || '').toLowerCase();
            } else if (col === 'valor_servicos') {
                valA = parseFloat(a.valor_servicos) || 0;
                valB = parseFloat(b.valor_servicos) || 0;
            } else if (col === 'status') {
                valA = (a.status || '').toLowerCase();
                valB = (b.status || '').toLowerCase();
            } else {
                valA = '';
                valB = '';
            }
            
            if (valA < valB) return -1 * order;
            if (valA > valB) return 1 * order;
            return 0;
        });
    }

    // Atualizar estatísticas de cabeçalho baseadas na lista filtrada!
    const totalFiltered = filtered.length;
    const emitidas = filtered.filter(n => n.tipo === "EMITIDA").length;
    const recebidas = filtered.filter(n => n.tipo === "RECEBIDA").length;
    const totalValor = filtered.reduce((acc, n) => acc + (parseFloat(n.valor_servicos) || 0), 0);

    document.getElementById("notas-stat-total").innerText = totalFiltered;
    document.getElementById("notas-stat-emitidas").innerText = emitidas;
    document.getElementById("notas-stat-recebidas").innerText = recebidas;
    document.getElementById("notas-stat-valor").innerText = formatCurrency(totalValor);

    // Renderizar corpo da tabela
    const tbody = document.getElementById("notas-table-body");
    if (!tbody) return;
    tbody.innerHTML = "";

    if (filtered.length === 0) {
        tbody.innerHTML = `<tr><td colspan="10" class="text-center py-20 text-on-surface-variant">Nenhuma nota fiscal encontrada para o filtro selecionado.</td></tr>`;
        document.getElementById("notas-paging-msg").innerText = "Mostrando 0 de 0 notas";
        document.getElementById("btn-notas-page-prev").setAttribute("disabled", "true");
        document.getElementById("btn-notas-page-next").setAttribute("disabled", "true");
        return;
    }

    // Lógica de paginação
    const page = AppState.notesPage;
    const limit = AppState.notesLimit;
    const totalPages = Math.ceil(filtered.length / limit) || 1;
    const shownStart = (page - 1) * limit + 1;
    const shownEnd = Math.min(page * limit, filtered.length);
    document.getElementById("notas-paging-msg").innerText = `Mostrando ${shownStart} a ${shownEnd} de ${filtered.length} notas (Pág. ${page}/${totalPages})`;

    const paginated = filtered.slice(shownStart - 1, shownEnd);

    paginated.forEach(nota => {
        const tr = document.createElement("tr");
        tr.className = "hover:bg-surface-container-low transition-colors border-b border-border/30";
        
        let statusBadge = "bg-success/10 text-success border-success/30";
        if (nota.status === "CANCELADA") statusBadge = "bg-error/10 text-error border-error/30";
        if (nota.status === "SUBSTITUIDA") statusBadge = "bg-warning/10 text-warning border-warning/30";

        const isChecked = AppState.selectedNotas.has(nota.id) ? 'checked' : '';

        tr.innerHTML = `
            <td class="px-6 py-3 w-8">
                <input type="checkbox" value="${nota.id}" ${isChecked} onchange="toggleSelectNota(this)" class="h-4.5 w-4.5 text-primary border-border rounded focus:ring-primary nota-selector">
            </td>
            <td class="px-4 py-3 font-mono font-bold text-on-surface">${nota.numero || "-"}</td>
            <td class="px-4 py-3 font-mono text-on-surface-variant">${nota.numero_dps || "-"}</td>
            <td class="px-4 py-3 font-mono text-on-surface-variant">${nota.serie || "0"}</td>
            <td class="px-4 py-3 text-on-surface-variant">${formatShortDate(nota.data_emissao)}</td>
            <td class="px-6 py-3 text-on-surface max-w-[200px]" title="${nota.prestador_nome || nota.prestador_cnpj_formatado}">
                <div class="font-semibold text-xs truncate">${nota.prestador_nome || "Emitente Desconhecido"}</div>
                <div class="text-[10px] text-on-surface-variant truncate">${nota.prestador_cnpj_formatado}</div>
            </td>
            <td class="px-6 py-3 text-on-surface max-w-[200px]" title="${nota.tomador_nome || nota.tomador_cnpj_formatado}">
                <div class="font-semibold text-xs truncate">${nota.tomador_nome || "Tomador Desconhecido"}</div>
                <div class="text-[10px] text-on-surface-variant truncate">${nota.tomador_cnpj_formatado}</div>
            </td>
            <td class="px-6 py-3 text-right font-bold text-on-surface">${formatCurrency(nota.valor_servicos)}</td>
            <td class="px-4 py-3 text-center">
                <span class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold border ${statusBadge}">
                    ${nota.status}
                </span>
            </td>
            <td class="px-6 py-3 text-center">
                <div class="flex items-center justify-center gap-1">
                    <button onclick="openPreviewModal(${nota.id})" class="h-7 w-7 rounded-md bg-primary/10 text-primary flex items-center justify-center hover:bg-primary/20 transition-all" title="Visualizar Nota">
                        <span class="material-symbols-outlined text-[16px]">visibility</span>
                    </button>
                    <button onclick="baixarXMLFisico(${nota.id})" class="h-7 w-7 rounded-md bg-secondary-container text-on-secondary-container flex items-center justify-center hover:bg-surface-container-high transition-all" title="Baixar XML">
                        <span class="material-symbols-outlined text-[16px]">download</span>
                    </button>
                </div>
            </td>
        `;
        tbody.appendChild(tr);
    });

    const btnPrev = document.getElementById("btn-notas-page-prev");
    const btnNext = document.getElementById("btn-notas-page-next");

    btnPrev.onclick = () => {
        if (page > 1) {
            AppState.notesPage = page - 1;
            renderNotasTable();
        }
    };
    btnNext.onclick = () => {
        if (page < totalPages) {
            AppState.notesPage = page + 1;
            renderNotasTable();
        }
    };

    if (page <= 1) btnPrev.setAttribute("disabled", "true");
    else btnPrev.removeAttribute("disabled");

    if (page >= totalPages) btnNext.setAttribute("disabled", "true");
    else btnNext.removeAttribute("disabled");

    // Inicializar as colunas redimensionáveis
    setTimeout(initTableResizable, 100);
}

function toggleSelectNota(checkbox) {
    const id = parseInt(checkbox.value);
    if (checkbox.checked) {
        AppState.selectedNotas.add(id);
    } else {
        AppState.selectedNotas.delete(id);
    }
    updateSelectedNotasCount();
}

function toggleSelectAllNotas() {
    const checkAll = document.getElementById("notas-select-all");
    const checkboxes = document.querySelectorAll("#notas-table-body .nota-selector");
    
    checkboxes.forEach(cb => {
        cb.checked = checkAll.checked;
        const id = parseInt(cb.value);
        if (checkAll.checked) {
            AppState.selectedNotas.add(id);
        } else {
            AppState.selectedNotas.delete(id);
        }
    });
    updateSelectedNotasCount();
}

function updateSelectedNotasCount() {
    const count = AppState.selectedNotas.size;
    document.getElementById("notas-selected-counter").innerText = `${count} nota(s) selecionada(s)`;
}

async function notasBatchAction(formato) {
    if (AppState.selectedNotas.size === 0) {
        showToast("Selecione pelo menos uma nota para aplicar ação em lote", "warning");
        return;
    }

    const ids = Array.from(AppState.selectedNotas);

    if (formato === 'sincronizar') {
        try {
            showToast("Disparando consulta de status na Receita Federal...", "info");
            const response = await fetch("/api/notas/sincronizar", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(ids)
            });

            const res = await response.json();
            if (!response.ok) throw new Error(res.detail || "Erro de API");

            switchView('downloads');
            
            const terminal = document.getElementById("dl-terminal");
            if (terminal) terminal.innerHTML = `<p class="text-neutral-500">// Consultando eventos ativos de NFS-e...</p>`;
            AppState.lastPolledLogIndex = 0;
            document.getElementById("dl-stats-container").classList.add("hidden");

            startLogPolling(res.download_id);

        } catch (e) {
            showToast(`Falha: ${e.message}`, "error");
        }
    } else {
        // Downloads Excel/XML/PDF ZIP
        try {
            showToast("Preparando exportação de arquivos...", "info");
            const response = await fetch(`/api/notas/exportar?formato=${formato}`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(ids)
            });

            if (!response.ok) throw new Error("Erro de exportação do servidor.");

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            
            const extensions = { 'excel': 'xlsx', 'xml': 'zip', 'pdf': 'zip' };
            const ext = extensions[formato] || 'zip';
            
            a.download = `exportacao_${formato}_${new Date().toISOString().split('T')[0]}.${ext}`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            
            showToast("Arquivo gerado e baixado com sucesso!", "success");

        } catch (e) {
            showToast(`Erro na exportação: ${e.message}`, "error");
        }
    }
}

function baixarXMLFisico(notaId) {
    window.open(`/api/notas/${notaId}/xml`, '_blank');
}

// 9. MODAL PREVIEW DE XML E PDF DANFSE
let activePreviewNotaId = null;
let activePreviewTab = 'pdf';

async function openPreviewModal(notaId) {
    activePreviewNotaId = notaId;
    const modal = document.getElementById("preview-modal");
    if (!modal) return;

    setPreviewTab('pdf');

    modal.classList.remove("hidden");
    void modal.offsetWidth;
    modal.classList.add("active");
}

function closePreviewModal() {
    const modal = document.getElementById("preview-modal");
    if (modal) {
        modal.classList.remove("active");
        setTimeout(() => {
            modal.classList.add("hidden");
            document.getElementById("preview-pdf-iframe").src = "";
            document.getElementById("preview-xml-console").innerText = "";
        }, 250);
    }
}

async function setPreviewTab(tab) {
    activePreviewTab = tab;
    
    const btnPdf = document.getElementById("btn-preview-pdf");
    const btnXml = document.getElementById("btn-preview-xml");
    const iframe = document.getElementById("preview-pdf-iframe");
    const consoleBox = document.getElementById("preview-xml-console");

    btnPdf.className = "h-8 px-4 rounded-md text-xs font-bold text-on-surface-variant hover:bg-surface-container-high transition-all";
    btnXml.className = "h-8 px-4 rounded-md text-xs font-bold text-on-surface-variant hover:bg-surface-container-high transition-all";
    iframe.classList.add("hidden");
    consoleBox.classList.add("hidden");

    if (tab === 'pdf') {
        btnPdf.className = "h-8 px-4 rounded-md text-xs font-bold bg-primary/10 text-primary transition-all";
        iframe.src = `/api/notas/${activePreviewNotaId}/pdf`;
        iframe.classList.remove("hidden");
    } else {
        btnXml.className = "h-8 px-4 rounded-md text-xs font-bold bg-primary/10 text-primary transition-all";
        consoleBox.classList.remove("hidden");
        consoleBox.innerText = "Carregando XML formatado...";

        try {
            const response = await fetch(`/api/notas/${activePreviewNotaId}/xml`);
            const text = await response.text();
            consoleBox.innerText = formatXml(text);
        } catch {
            consoleBox.innerText = "Erro ao ler arquivo XML.";
        }
    }
}

function formatXml(xml) {
    let formatted = '';
    let reg = /(>)(<)(\/*)/g;
    xml = xml.replace(reg, '$1\r\n$2$3');
    let pad = 0;
    xml.split('\r\n').forEach(node => {
        let indent = 0;
        if (node.match( /.+<\/\w[^>]*>$/ )) {
            indent = 0;
        } else if (node.match( /^<\/\w/ )) {
            if (pad !== 0) pad -= 1;
        } else if (node.match( /^<\w[^>]*[^\/]>.*$/ )) {
            indent = 1;
        } else {
            indent = 0;
        }

        let padding = '';
        for (let i = 0; i < pad; i++) padding += '  ';
        formatted += padding + node + '\r\n';
        pad += indent;
    });
    return formatted.trim();
}

function downloadPreviewFile(formato) {
    if (!activePreviewNotaId) return;
    if (formato === 'xml') {
        baixarXMLFisico(activePreviewNotaId);
    } else {
        window.open(`/api/notas/${activePreviewNotaId}/pdf`, '_blank');
    }
}

// 10. ABA DASHBOARD COM BENTO ANALYTICS E CHARTJS
async function refreshDashboard() {
    try {
        // 1. Estatísticas Bento Grid
        const statsRes = await fetch("/api/dashboard/estatisticas");
        if (statsRes.ok) {
            const stats = await statsRes.json();
            
            document.getElementById("dash-faturamento-total").innerText = formatCurrency(stats.valor_total_emitido);
            document.getElementById("dash-total-notas").innerText = stats.total_notas.toLocaleString('pt-BR');
            document.getElementById("dash-total-empresas").innerText = stats.total_empresas;
            document.getElementById("dash-erros-recentes").innerText = stats.erros_recentes;
            
            const deltaLabel = document.getElementById("dash-notas-novas-delta");
            if (deltaLabel) {
                deltaLabel.innerText = `+${stats.total_emitidas} emitidas`;
            }
        }

        // 2. Ranking de faturamento do mês nas empresas
        const rankingBox = document.getElementById("dash-ranking-empresas");
        if (rankingBox) {
            const fatRes = await fetch("/api/dashboard/faturamento");
            if (fatRes.ok) {
                const fatData = await fatRes.json();
                
                rankingBox.innerHTML = "";
                const rankingList = fatData.faturamento_empresas || [];
                
                if (rankingList.length > 0) {
                    // Ordenar por faturamento acumulado decrescente
                    const sorted = [...rankingList].sort((a,b) => b.valor - a.valor);
                    
                    sorted.forEach((item, index) => {
                        const div = document.createElement("div");
                        div.className = "ranking-item";
                        div.innerHTML = `
                            <div class="flex items-center gap-2">
                                <span class="w-5 h-5 rounded-full bg-primary/10 text-primary flex items-center justify-center font-bold text-[10px]">${index+1}</span>
                                <span class="font-semibold text-on-surface line-clamp-1 max-w-[120px]" title="${item.empresa}">${item.empresa}</span>
                            </div>
                            <div class="text-right">
                                <div class="font-bold text-on-surface">${formatCurrency(item.valor)}</div>
                                <div class="text-[9px] text-on-surface-variant font-medium">${item.notas} notas no período</div>
                            </div>
                        `;
                        rankingBox.appendChild(div);
                    });
                } else {
                    rankingBox.innerHTML = `<p class="text-xs text-on-surface-variant text-center py-10">Nenhum faturamento catalogado no mês.</p>`;
                }

                // 3. Montar/Atualizar Gráfico de Barras Chart.js
                renderFaturamentoChart(fatData.faturamento_mensal || []);
            }
        }

    } catch (e) {
        console.error("Falha ao carregar dashboard", e);
    }
}

function renderFaturamentoChart(historico) {
    const ctx = document.getElementById('faturamentoChart');
    if (!ctx) return;

    AppState.faturamentoChartData = historico;

    if (AppState.faturamentoChart) {
        AppState.faturamentoChart.destroy();
    }

    if (historico.length === 0) {
        historico = [
            { mes: 'Jan', valor: 0 }, { mes: 'Fev', valor: 0 }, { mes: 'Mar', valor: 0 },
            { mes: 'Abr', valor: 0 }, { mes: 'Mai', valor: 0 }, { mes: 'Jun', valor: 0 }
        ];
    }

    const labels = historico.map(h => h.mes || "");
    const valores = historico.map(h => h.valor || 0);

    // Paleta de gráficos validada para daltonismo/contraste (identidade "Razão Azul")
    const isDark = document.documentElement.classList.contains('dark');
    const serie1 = isDark ? '#4093CD' : '#1668A0';
    const gridColor = isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(27, 37, 48, 0.05)';
    const axisColor = isDark ? '#A7B4C0' : '#495A6B';

    AppState.faturamentoChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Faturamento Mensal Emitido (Competência)',
                data: valores,
                backgroundColor: serie1,
                borderRadius: 8,
                hoverBackgroundColor: isDark ? '#55A3D6' : '#15679A'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: function(value) {
                            return 'R$ ' + value.toLocaleString('pt-BR');
                        },
                        font: { size: 10 },
                        color: axisColor
                    },
                    grid: { color: gridColor }
                },
                x: {
                    grid: { display: false },
                    ticks: { font: { size: 10 }, color: axisColor }
                }
            }
        }
    });
}

// 11. ABA DE APURAÇÃO DE FATURAMENTO / RELATÓRIOS DETALHADOS (BENTO APURAÇÃO)
function setFaturamentoFilter(type) {
    AppState.faturamentoFilterType = type;
    const btnComp = document.getElementById("btn-fat-comp");
    const btnEmis = document.getElementById("btn-fat-emis");

    if (type === 'competencia') {
        if (btnComp) btnComp.className = "flex-1 rounded-md text-xs font-bold bg-surface shadow-xs text-primary transition-all duration-200";
        if (btnEmis) btnEmis.className = "flex-1 rounded-md text-xs font-bold text-on-surface-variant hover:bg-surface-container-highest transition-all duration-200";
    } else {
        if (btnEmis) btnEmis.className = "flex-1 rounded-md text-xs font-bold bg-surface shadow-xs text-primary transition-all duration-200";
        if (btnComp) btnComp.className = "flex-1 rounded-md text-xs font-bold text-on-surface-variant hover:bg-surface-container-highest transition-all duration-200";
    }
}

async function gerarRelatorioFaturamento() {
    const mes = document.getElementById("fat-mes-select").value;
    const ano = document.getElementById("fat-ano-select").value;
    const campoData = AppState.faturamentoFilterType;

    const tbody = document.getElementById("faturamento-table-body");
    const containerDet = document.getElementById("faturamento-detalhes-container");
    const reportContainer = document.getElementById("faturamento-report-container");

    if (tbody) tbody.innerHTML = `<tr><td colspan="5" class="text-center py-20 text-on-surface-variant"><span class="animate-pulse flex items-center justify-center gap-1.5"><span class="material-symbols-outlined text-[20px] animate-spin">sync</span> Carregando apurações...</span></td></tr>`;
    if (containerDet) containerDet.innerHTML = `<p class="text-xs text-on-surface-variant text-center py-10">Calculando indicadores...</p>`;
    if (reportContainer) reportContainer.classList.add("hidden");

    // Formatar datas para abranger todo o mês
    const m = mes.padStart(2, '0');
    const dataInicio = `${ano}-${m}-01`;
    const lastDay = new Date(ano, parseInt(mes), 0).getDate();
    const dataFim = `${ano}-${m}-${lastDay}`;

    // Buscar notas emitidas normais no período
    let url = `/api/notas?page=1&limit=10000&tipo=EMITIDA&campo_data=${campoData}&data_inicio=${dataInicio}&data_fim=${dataFim}`;

    try {
        const response = await fetch(url);
        if (!response.ok) throw new Error("Erro de servidor ao apurar faturamento.");

        const data = await response.json();
        AppState.faturamentoReportNotes = data.notas || [];

        // Agrupar faturamento por empresa cadastrada
        const faturamentoGrupos = {};
        AppState.empresas.forEach(emp => {
            faturamentoGrupos[emp.id] = {
                empresa_id: emp.id,
                razao_social: emp.razao_social,
                cnpj: emp.cnpj,
                cnpj_formatado: emp.cnpj_formatado,
                total_notas: 0,
                valor_acumulado: 0.0
            };
        });

        // Somar notas
        AppState.faturamentoReportNotes.forEach(nota => {
            if (faturamentoGrupos[nota.empresa_id]) {
                faturamentoGrupos[nota.empresa_id].total_notas++;
                faturamentoGrupos[nota.empresa_id].valor_acumulado += parseFloat(nota.valor_servicos || 0);
            }
        });

        // Calcular totais gerais
        const listGrupos = Object.values(faturamentoGrupos);
        const totalValorPeriodo = listGrupos.reduce((acc, c) => acc + c.valor_acumulado, 0.0);
        const totalEmpresasAtivas = listGrupos.filter(g => g.total_notas > 0).length;
        const totalNotasEmitidas = listGrupos.reduce((acc, c) => acc + c.total_notas, 0);

        // Atualizar estatísticas de apuração
        document.getElementById("fat-total-valor").innerText = formatCurrency(totalValorPeriodo);
        document.getElementById("fat-total-empresas").innerText = totalEmpresasAtivas;
        document.getElementById("fat-total-notas").innerText = totalNotasEmitidas;

        // Renderizar Tabela Resumo
        if (tbody) {
            tbody.innerHTML = "";
            listGrupos.forEach(grp => {
                const tr = document.createElement("tr");
                tr.className = "hover:bg-surface-container-low transition-colors border-b border-border/30";
                tr.innerHTML = `
                    <td class="px-6 py-4 font-semibold text-on-surface">${grp.razao_social}</td>
                    <td class="px-6 py-4 font-mono text-on-surface-variant">${grp.cnpj_formatado}</td>
                    <td class="px-6 py-4 text-right font-semibold text-on-surface">${grp.total_notas}</td>
                    <td class="px-6 py-4 text-right font-bold text-primary">${formatCurrency(grp.valor_acumulado)}</td>
                    <td class="px-6 py-4 text-center">
                        <div class="flex items-center justify-center gap-1.5">
                            <button onclick="downloadEmpresaFaturamentoZip(${grp.empresa_id})" class="p-1 hover:bg-surface-container rounded-md text-primary" title="Baixar ZIP XMLs">
                                <span class="material-symbols-outlined text-[18px]">folder_zip</span>
                            </button>
                            <button onclick="downloadEmpresaFaturamentoExcel(${grp.empresa_id})" class="p-1 hover:bg-surface-container rounded-md text-success" title="Exportar Planilha Excel">
                                <span class="material-symbols-outlined text-[18px]">analytics</span>
                            </button>
                        </div>
                    </td>
                `;
                tbody.appendChild(tr);
            });
        }

        // Renderizar Expanders de Detalhes
        if (containerDet) {
            containerDet.innerHTML = "";
            listGrupos.forEach(grp => {
                const detailsBox = document.createElement("details");
                detailsBox.className = "group bg-surface border border-border/60 rounded-xl overflow-hidden shadow-xs [&_summary::-webkit-details-marker]:hidden";
                
                detailsBox.innerHTML = `
                    <summary class="flex justify-between items-center p-4 cursor-pointer select-none bg-surface-bright/50 hover:bg-surface-container-low transition-colors">
                        <div class="flex items-center gap-3">
                            <span class="material-symbols-outlined text-primary group-open:rotate-180 transition-transform duration-200">expand_more</span>
                            <div>
                                <h4 class="font-bold text-xs text-on-surface">${grp.razao_social}</h4>
                                <p class="text-[10px] text-on-surface-variant">CNPJ: ${grp.cnpj_formatado}</p>
                            </div>
                        </div>
                        <div class="text-right">
                            <span class="text-xs font-bold text-primary">${formatCurrency(grp.valor_acumulado)}</span>
                            <span class="text-[10px] text-on-surface-variant ml-2">(${grp.total_notas} Notas)</span>
                        </div>
                    </summary>
                    <div class="p-4 border-t border-t-border/40 bg-surface space-y-3.5 text-xs">
                        <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
                            <div class="bg-surface-container-low p-3 rounded-lg border border-border/20">
                                <span class="text-[10px] text-on-surface-variant uppercase tracking-wider font-semibold block">Faturamento Bruto</span>
                                <p class="font-bold mt-1 text-on-surface">${formatCurrency(grp.valor_acumulado)}</p>
                            </div>
                            <div class="bg-surface-container-low p-3 rounded-lg border border-border/20">
                                <span class="text-[10px] text-on-surface-variant uppercase tracking-wider font-semibold block">Notas Emitidas</span>
                                <p class="font-bold mt-1 text-on-surface">${grp.total_notas}</p>
                            </div>
                            <div class="bg-surface-container-low p-3 rounded-lg border border-border/20">
                                <span class="text-[10px] text-on-surface-variant uppercase tracking-wider font-semibold block">Último NSU Lido</span>
                                <p class="font-bold mt-1 text-primary font-mono">${AppState.empresas.find(e=>e.id===grp.empresa_id)?.ultimo_nsu || 0}</p>
                            </div>
                            <div class="bg-surface-container-low p-3 rounded-lg border border-border/20">
                                <span class="text-[10px] text-on-surface-variant uppercase tracking-wider font-semibold block">Data Próxima Busca</span>
                                <p class="font-bold mt-1 text-on-surface">Agendado</p>
                            </div>
                        </div>
                    </div>
                `;
                containerDet.appendChild(detailsBox);
            });
        }

        // Revelar relatório
        if (reportContainer) reportContainer.classList.remove("hidden");
        showToast("Relatório de apuração consolidado com sucesso!", "success");

    } catch (e) {
        showToast(`Erro na apuração: ${e.message}`, "error");
    }
}

// Exportações específicas da aba faturamento
async function downloadEmpresaFaturamentoZip(empresaId) {
    const ids = AppState.faturamentoReportNotes.filter(n => n.empresa_id === empresaId).map(n => n.id);
    if (ids.length === 0) {
        showToast("Nenhuma nota disponível para baixar.", "warning");
        return;
    }
    
    // Baixar ZIP
    try {
        showToast("Gerando arquivo compactado de XMLs...", "info");
        const response = await fetch(`/api/notas/exportar?formato=xml`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(ids)
        });

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `xmls_faturamento_empresa_${empresaId}.zip`;
        document.body.appendChild(a);
        a.click();
        a.remove();
    } catch {
        showToast("Erro ao baixar XMLs.", "error");
    }
}

async function downloadEmpresaFaturamentoExcel(empresaId) {
    const ids = AppState.faturamentoReportNotes.filter(n => n.empresa_id === empresaId).map(n => n.id);
    if (ids.length === 0) {
        showToast("Nenhuma nota disponível para exportar.", "warning");
        return;
    }
    
    // Baixar Excel
    try {
        showToast("Gerando planilha Excel...", "info");
        const response = await fetch(`/api/notas/exportar?formato=excel`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(ids)
        });

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `planilha_faturamento_empresa_${empresaId}.xlsx`;
        document.body.appendChild(a);
        a.click();
        a.remove();
    } catch {
        showToast("Erro ao baixar planilha.", "error");
    }
}

async function downloadAllFaturamentoZip() {
    const ids = AppState.faturamentoReportNotes.map(n => n.id);
    if (ids.length === 0) {
        showToast("Nenhuma nota cadastrada no período selecionado.", "warning");
        return;
    }

    try {
        showToast("Processando e compactando notas de todos contribuintes...", "info");
        const response = await fetch(`/api/notas/exportar?formato=xml`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(ids)
        });

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `todos_xmls_faturamento_${new Date().toISOString().split('T')[0]}.zip`;
        document.body.appendChild(a);
        a.click();
        a.remove();
    } catch {
        showToast("Falha na exportação em lote.", "error");
    }
}

// 12. ABA DE AUTOMAÇÕES E AGENDAMENTOS (SCHEDULER)
let activeSchedulerMode = 'intervalo';
function setSchedulerMode(mode) {
    activeSchedulerMode = mode;
    
    const btnInt = document.getElementById("btn-sched-mode-int");
    const btnFix = document.getElementById("btn-sched-mode-fix");
    const intField = document.getElementById("sched-interval-field");
    const timeField = document.getElementById("sched-time-field");

    if (mode === 'intervalo') {
        if (btnInt) btnInt.className = "flex-1 py-2 text-xs font-semibold rounded-lg bg-surface text-primary shadow-xs transition-all";
        if (btnFix) btnFix.className = "flex-1 py-2 text-xs font-semibold rounded-lg text-on-surface-variant hover:bg-surface-container-high transition-all";
        if (intField) intField.classList.remove("hidden");
        if (timeField) timeField.classList.add("hidden");
    } else {
        if (btnFix) btnFix.className = "flex-1 py-2 text-xs font-semibold rounded-lg bg-surface text-primary shadow-xs transition-all";
        if (btnInt) btnInt.className = "flex-1 py-2 text-xs font-semibold rounded-lg text-on-surface-variant hover:bg-surface-container-high transition-all";
        if (timeField) timeField.classList.remove("hidden");
        if (intField) intField.classList.add("hidden");
    }
}

async function refreshAgendamentos() {
    try {
        const response = await fetch("/api/agendador/status");
        if (!response.ok) throw new Error("Erro ao consultar status.");

        const status = await response.json();
        
        // 1. Atualizar banner de status
        const banner = document.getElementById("sched-status-banner");
        const icon = document.getElementById("sched-status-icon");
        const title = document.getElementById("sched-status-title");
        const desc = document.getElementById("sched-status-desc");
        const btnToggle = document.getElementById("btn-sched-toggle");

        if (status.scheduler_ativo) {
            banner.className = "mb-6 p-4 rounded-xl border bg-success/10 border-success/30 text-success flex items-start gap-3 shadow-xs";
            if (icon) {
                icon.className = "material-symbols-outlined text-3xl text-success";
                icon.innerText = "check_circle";
            }
            title.innerText = "Agendador Automático Ligado!";
            desc.innerText = `Próxima busca agendada para: ${status.proxima_execucao || "Indefinida/Manual"}`;
            
            if (btnToggle) {
                btnToggle.innerText = "Desligar Agendamento Automático";
                btnToggle.className = "w-full h-12 bg-error text-on-primary rounded-full font-bold text-label-lg flex items-center justify-center gap-2 hover:opacity-90 active:scale-95 shadow-xs transition-all";
            }
        } else {
            banner.className = "mb-6 p-4 rounded-xl border bg-secondary-container/50 border-border/80 text-on-surface-variant flex items-start gap-3 shadow-xs";
            if (icon) {
                icon.className = "material-symbols-outlined text-3xl text-on-surface-variant";
                icon.innerText = "cancel";
            }
            title.innerText = "Agendador Automático Desativado";
            desc.innerText = "O agendador não executará buscas automáticas no background.";
            
            if (btnToggle) {
                btnToggle.innerText = "Ativar Agendador Automático";
                btnToggle.className = "w-full h-12 bg-primary text-on-primary rounded-full font-bold text-label-lg flex items-center justify-center gap-2 hover:opacity-90 active:scale-95 shadow-xs transition-all";
            }
        }

        // 2. Preencher formulário de parâmetros
        const config = status.config;
        if (config) {
            setSchedulerMode(config.modo || 'intervalo');
            document.getElementById("sched-interval").value = config.intervalo_horas || 6;
            document.getElementById("sched-time").value = config.horario || "08:00";
        }

        // 3. Preencher tabela de histórico de execuções
        const tbody = document.getElementById("scheduler-history-body");
        if (tbody) {
            tbody.innerHTML = "";
            if (status.historico.length === 0) {
                tbody.innerHTML = `<tr><td colspan="6" class="text-center py-12 text-on-surface-variant">Nenhuma execução registrada no banco de dados.</td></tr>`;
            } else {
                status.historico.forEach(log => {
                    let logStatus = "bg-success/10 text-success border-success/30";
                    let logText = "Sucesso";
                    if (log.erros > 0) {
                        logStatus = "bg-error/10 text-error border-error/30";
                        logText = "Falha/Alerta";
                    }

                    const tr = document.createElement("tr");
                    tr.className = "hover:bg-surface-container-low transition-colors border-b border-border/30";
                    tr.innerHTML = `
                        <td class="px-4 py-3 font-semibold text-on-surface">${log.data}</td>
                        <td class="px-4 py-3 text-on-surface max-w-[150px]" title="${log.empresa_nome || "Todos contribuintes"}"><div class="truncate">${log.empresa_nome || "Todos contribuintes"}</div></td>
                        <td class="px-3 py-3 text-right font-bold text-on-surface">${log.notas_novas}</td>
                        <td class="px-3 py-3 text-right text-on-surface">${log.status_atualizados}</td>
                        <td class="px-3 py-3 text-right text-error font-semibold">${log.erros}</td>
                        <td class="px-3 py-3 text-center">
                             <span class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold border ${logStatus}">
                                <strong>${logText}</strong>
                            </span>
                        </td>
                    `;
                    tbody.appendChild(tr);
                });
            }
        }

        // 4. Se estiver executando no background, iniciar/manter polling e ajustar botão manual
        if (status.executando) {
            startSchedulerPolling();
            const btnManual = document.getElementById("btn-sched-manual");
            if (btnManual) {
                btnManual.setAttribute("disabled", "true");
                btnManual.innerHTML = `<span class="material-symbols-outlined text-[20px] animate-spin">sync</span> Sincronizando...`;
            }
        } else {
            stopSchedulerPolling();
            const btnManual = document.getElementById("btn-sched-manual");
            if (btnManual) {
                btnManual.removeAttribute("disabled");
                btnManual.innerHTML = `<span class="material-symbols-outlined text-[20px]">rocket_launch</span> Rodar Sincronização Agora`;
            }
        }

    } catch (e) {
        showToast(`Falha ao ler agendador: ${e.message}`, "error");
    }
}

function startSchedulerPolling() {
    if (AppState.schedulerPollingInterval) return;
    
    AppState.schedulerPollingInterval = setInterval(() => {
        if (AppState.currentView === 'agendamentos') {
            refreshAgendamentos();
        } else {
            stopSchedulerPolling();
        }
    }, 3000);
}

function stopSchedulerPolling() {
    if (AppState.schedulerPollingInterval) {
        clearInterval(AppState.schedulerPollingInterval);
        AppState.schedulerPollingInterval = null;
    }
}

async function toggleScheduler() {
    const isAct = document.getElementById("sched-status-title").innerText.includes("Ligado");
    
    // Obter parâmetros do formulário
    const modo = activeSchedulerMode;
    const intervalo = document.getElementById("sched-interval").value;
    const horario = document.getElementById("sched-time").value;

    const form = new FormData();
    form.append("ativo", !isAct ? "true" : "false");
    form.append("modo", modo);
    form.append("intervalo_horas", intervalo);
    form.append("horario", horario);

    try {
        const response = await fetch("/api/agendador/configurar", {
            method: "POST",
            body: form
        });

        const res = await response.json();
        if (response.ok && res.success) {
            showToast(!isAct ? "Agendador automático ativado!" : "Agendador automático desativado.", "success");
            refreshAgendamentos();
        } else {
            throw new Error(res.detail || "Erro de configuração.");
        }
    } catch (e) {
        showToast(`Erro ao alterar agendador: ${e.message}`, "error");
    }
}

async function triggerManualScheduler() {
    const btn = document.getElementById("btn-sched-manual");
    try {
        showToast("Iniciando varredura manual de todos contribuintes ativos...", "info");
        if (btn) btn.setAttribute("disabled", "true");

        const response = await fetch("/api/agendador/executar", { method: "POST" });
        const res = await response.json();
        
        if (response.ok && res.success) {
            showToast("Busca em segundo plano disparada com sucesso!", "success");
            refreshAgendamentos();
        } else {
            throw new Error(res.error || "Falha de execução.");
        }
    } catch (e) {
        showToast(`Erro ao rodar: ${e.message}`, "error");
    } finally {
        if (btn) btn.removeAttribute("disabled");
    }
}

// 13. ABA CONFIGURAÇÕES E BACKUPS DO SISTEMA
async function refreshConfig() {
    // Carregar caminho customizado dos XMLs na interface
    carregarConfigXmlsDir();

    const list = document.getElementById("config-backups-list");
    if (!list) return;

    list.innerHTML = `<p class="text-xs text-on-surface-variant text-center py-6">Consultando backups físicos...</p>`;

    try {
        const response = await fetch("/api/backup");
        if (!response.ok) throw new Error("Falha ao ler diretório de backups");

        const backups = await response.json();
        
        list.innerHTML = "";
        if (backups.length === 0) {
            list.innerHTML = `<p class="text-xs text-on-surface-variant text-center py-6">Nenhum backup local encontrado.</p>`;
            return;
        }

        backups.forEach(bak => {
            const div = document.createElement("div");
            div.className = "flex justify-between items-center p-3 bg-surface-container rounded-xl border border-border/30 hover:border-primary/30 transition-all";
            div.innerHTML = `
                <div>
                    <h5 class="text-xs font-bold text-on-surface">${bak.nome}</h5>
                    <p class="text-[9px] text-on-surface-variant">${bak.data} | ${(bak.tamanho_mb).toFixed(2)} MB</p>
                </div>
                <div class="flex gap-1.5">
                    <button onclick="triggerRestoreBackup('${bak.nome}')" class="h-8 px-3 rounded-lg bg-primary/10 text-primary hover:bg-primary/20 text-[10px] font-bold transition-all">Restaurar</button>
                    <a href="/api/backup/baixar/${bak.nome}" class="h-8 w-8 bg-secondary-container text-on-secondary-container rounded-lg flex items-center justify-center hover:bg-surface-container-high transition-all" title="Baixar Backup"><span class="material-symbols-outlined text-[16px]">download</span></a>
                </div>
            `;
            list.appendChild(div);
        });

    } catch (e) {
        list.innerHTML = `<p class="text-xs text-error text-center py-6">Falha: ${e.message}</p>`;
    }
}

async function triggerCreateBackup() {
    try {
        showToast("Criando arquivo de backup compactado...", "info");
        const response = await fetch("/api/backup/criar", { method: "POST" });
        const res = await response.json();

        if (response.ok && res.success) {
            showToast("Backup compactado local gerado!", "success");
            addNotification("Backup de banco de dados compactado criado com sucesso!", "success");
            refreshConfig();
        } else {
            throw new Error(res.error || "Erro ao criar backup");
        }
    } catch (e) {
        showToast(`Erro ao criar backup: ${e.message}`, "error");
        addNotification(`Falha ao criar backup: ${e.message}`, "error");
    }
}

async function triggerRestoreBackup(filename) {
    if (!confirm(`⚠️ ALERTA CRÍTICO: Deseja realmente restaurar o backup "${filename}"?\nToda a base de dados SQLite atual e arquivos XML serão excluídos e substituídos por este backup!`)) {
        return;
    }

    try {
        showToast("Sobrescrevendo arquivos de banco e XMLs...", "info");
        const form = new FormData();
        form.append("nome_backup", filename);
        
        const response = await fetch(`/api/backup/restaurar`, { 
            method: "POST",
            body: form
        });
        const res = await response.json();

        if (response.ok && res.success) {
            showToast("Restauração concluída! Reiniciando frontend...", "success");
            addNotification(`Backup "${filename}" restaurado com sucesso!`, "success");
            setTimeout(() => window.location.reload(), 1500);
        } else {
            throw new Error(res.detail || "Erro de descompactação.");
        }
    } catch (e) {
        showToast(`Erro na restauração: ${e.message}`, "error");
        addNotification(`Erro ao restaurar backup: ${e.message}`, "error");
    }
}

async function triggerUploadBackup(event) {
    const file = event.target.files[0];
    if (!file) return;

    const form = new FormData();
    form.append("backup_file", file);

    try {
        showToast("Carregando e descompactando arquivo de backup externo...", "info");
        const response = await fetch("/api/backup/restaurar", {
            method: "POST",
            body: form
        });

        const res = await response.json();
        if (response.ok && res.success) {
            showToast("Backup restaurado e importado com sucesso!", "success");
            addNotification(`Backup externo "${file.name}" importado e restaurado com sucesso!`, "success");
            setTimeout(() => window.location.reload(), 1500);
        } else {
            throw new Error(res.detail || "Falha ao processar arquivo");
        }
    } catch (e) {
        showToast(`Erro na importação externa: ${e.message}`, "error");
        addNotification(`Falha na importação de backup: ${e.message}`, "error");
    } finally {
        document.getElementById("backup-file-input").value = "";
    }
}

// 14. TESTADOR DE CREDENCIAIS DE API (CABLE TEST /DFe/0)
async function triggerAPITest() {
    const empId = document.getElementById("test-empresa-select").value;
    if (!empId) {
        showToast("Selecione uma empresa cadastrada ativa", "warning");
        return;
    }

    const consoleBox = document.getElementById("test-console");
    if (consoleBox) consoleBox.innerHTML = `<p class="text-neutral-500">// Estabelecendo handshake SSL/TLS de certificado PFX... Aguarde.</p>`;

    try {
        showToast("Iniciando chamada REST para API Nacional...", "info");
        
        const form = new FormData();
        form.append("empresa_id", empId);

        const response = await fetch(`/api/teste-api`, { method: "POST", body: form });
        const res = await response.json();

        if (consoleBox) {
            consoleBox.innerHTML = "";
            const div = document.createElement("div");
            div.className = "log-line";
            
            if (response.ok && res.success) {
                showToast("Conexão validada com sucesso!", "success");
                addNotification("Conexão com a API Nacional validada com sucesso!", "success");
                div.innerHTML = `
                    <span class="log-success">▶️ CONEXÃO ESTABELECIDA COM SUCESSO!</span><br>
                    <span class="log-info">Autenticação:</span> Homologada via certificado A1<br>
                    <span class="log-info">Status Processamento:</span> ${res.status}<br>
                    <span class="log-info">Documentos Prontos para NSU:</span> ${res.documentos_encontrados}<br>
                    <span class="log-debug">Retorno JSON Completo:</span> ${JSON.stringify(res.resposta_completa)}
                `;
            } else {
                showToast("Falha na autenticação SSL/TLS.", "error");
                addNotification("Falha na conexão de teste com a API Nacional: certificado inválido ou rejeitado.", "error");
                div.innerHTML = `
                    <span class="log-error">❌ FALHA NA AUTENTICAÇÃO COM SERVIDOR NACIONAL!</span><br>
                    <span class="log-error">Motivo/Erro:</span> ${res.error || "Handshake SSL falhou ou senha do PFX está incorreta."}<br>
                    <span class="log-debug">Resposta Detalhada:</span> ${JSON.stringify(res)}
                `;
            }
            consoleBox.appendChild(div);
        }
    } catch (e) {
        showToast(`Erro técnico: ${e.message}`, "error");
        addNotification(`Erro técnico no teste de API: ${e.message}`, "error");
        if (consoleBox) {
            consoleBox.innerHTML = `<p class="text-red-500">Erro crítico de comunicação: ${e.message}</p>`;
        }
    }
}


// --- EXTRA SYSTEM CONFIGS & AUTO-UPDATER JAVASCRIPT ---

async function carregarConfigXmlsDir() {
    const input = document.getElementById("config-xmls-dir-input");
    if (!input) return;
    try {
        const response = await fetch("/api/config/xmls_dir");
        if (response.ok) {
            const data = await response.json();
            input.value = data.xmls_dir || "";
        }
    } catch (e) {
        console.error("Erro ao carregar caminho dos XMLs", e);
    }
}

async function salvarConfigXmlsDir() {
    const input = document.getElementById("config-xmls-dir-input");
    if (!input) return;
    const xmlsDir = input.value.trim();
    
    const form = new FormData();
    form.append("xmls_dir", xmlsDir);
    
    try {
        showToast("Salvando diretório de destino...", "info");
        const response = await fetch("/api/config/xmls_dir", {
            method: "POST",
            body: form
        });
        const res = await response.json();
        if (response.ok && res.success) {
            showToast("Diretório de destino salvo com sucesso!", "success");
            input.value = res.xmls_dir;
        } else {
            throw new Error(res.detail || "Erro ao salvar.");
        }
    } catch (e) {
        showToast(`Erro: ${e.message}`, "error");
    }
}

// Armazena a URL de download remota da nova versão
let remoteDownloadUrl = "";

async function checarAtualizacaoSistema() {
    const btn = document.getElementById("btn-checar-update");
    const infoBox = document.getElementById("updater-info-box");
    const title = document.getElementById("updater-info-title");
    const desc = document.getElementById("updater-info-desc");
    const notes = document.getElementById("updater-notes-box");
    
    if (btn) {
        btn.setAttribute("disabled", "true");
        btn.innerHTML = `<span class="material-symbols-outlined text-[16px] animate-spin">sync</span> Procurando...`;
    }
    
    try {
        showToast("Consultando servidor de atualizações...", "info");
        const response = await fetch("/api/atualizador/checar");
        if (!response.ok) throw new Error("Erro de conexão com o atualizador.");
        
        const data = await response.json();
        
        if (data.update_disponivel) {
            showToast("Nova versão do Fiscal Manager localizada!", "success");
            remoteDownloadUrl = data.url_download;
            
            if (title) title.innerText = `Nova Versão v${data.versao_remota} Disponível!`;
            if (desc) desc.innerText = `Versão local: v${data.versao_local} | Lançada em nuvem.`;
            if (notes) notes.innerHTML = `<strong>Notas da Versão:</strong><br>${data.notes_versao || data.notas_versao || 'Nenhuma nota fornecida.'}`;
            
            if (infoBox) infoBox.classList.remove("hidden");
        } else {
            showToast("Seu sistema está 100% atualizado!", "success");
            if (infoBox) infoBox.classList.add("hidden");
        }
    } catch (e) {
        showToast(`Falha na consulta: ${e.message}`, "error");
    } finally {
        if (btn) {
            btn.removeAttribute("disabled");
            btn.innerHTML = `<span class="material-symbols-outlined text-[16px]">sync</span> Procurando Atualizações`;
        }
    }
}

async function executarAtualizacaoSistema() {
    if (!remoteDownloadUrl) {
        showToast("Nenhuma URL de atualização configurada.", "warning");
        return;
    }
    
    if (!confirm("⚠️ CONFIRMAÇÃO DE ATUALIZAÇÃO:\nDeseja prosseguir com a atualização do sistema?\n\nO servidor será desligado em segundo plano e reiniciado automaticamente com os novos códigos. Todos os seus dados de empresas, certificados e notas fiscais salvos serão 100% preservados!")) {
        return;
    }
    
    const btn = document.getElementById("btn-executar-update");
    if (btn) {
        btn.setAttribute("disabled", "true");
        btn.innerHTML = `<span class="material-symbols-outlined text-[18px] animate-spin font-bold">autorenew</span> Atualizando sistema... Aguarde.`;
    }
    
    try {
        const form = new FormData();
        form.append("url_download", remoteDownloadUrl);
        
        showToast("Baixando pacote estável e preparando extração...", "info");
        const response = await fetch("/api/atualizador/executar", {
            method: "POST",
            body: form
        });
        
        const res = await response.json();
        if (response.ok && res.success) {
            // NÃO dizer "concluído" aqui: o updater ainda vai rodar em segundo
            // plano. A confirmação real vem depois, quando o novo servidor sobe
            // e o app lê o resultado da atualização (verificarResultadoAtualizacao).
            showToast("Pacote baixado. Aplicando e reiniciando o sistema...", "info");

            // Polling de recarregamento para aguardar o boot do novo servidor
            let attempts = 0;
            const reloadInterval = setInterval(async () => {
                attempts++;
                try {
                    const chk = await fetch("/api/agendador/status");
                    if (chk.ok) {
                        clearInterval(reloadInterval);
                        // O aviso de sucesso/falha real é dado por
                        // verificarResultadoAtualizacao() após o reload.
                        setTimeout(() => window.location.reload(), 1000);
                    }
                } catch (err) {
                    if (attempts > 20) {
                        clearInterval(reloadInterval);
                        showToast("O sistema não voltou sozinho. Verifique se a atualização foi aplicada ou rode o Iniciar_Sistema.bat.", "warning");
                    }
                }
            }, 2000);
        } else {
            throw new Error(res.detail || "Falha na execução.");
        }
    } catch (e) {
        showToast(`Erro na atualização: ${e.message}`, "error");
        if (btn) {
            btn.removeAttribute("disabled");
            btn.innerHTML = `<span class="material-symbols-outlined text-[18px]">download_for_offline</span> Atualizar e Reiniciar Agora`;
        }
    }
}

// Ao iniciar, confere se a última atualização aplicou todos os arquivos.
// Fecha a lacuna do "sucesso silencioso": se algum arquivo não foi trocado,
// o usuário é avisado de forma clara em vez de o sistema quebrar sem explicação.
async function verificarResultadoAtualizacao() {
    try {
        const response = await fetch("/api/atualizador/resultado");
        if (!response.ok) return;
        const data = await response.json();
        if (!data.tem_resultado) return;

        if (data.sucesso) {
            const msg = `Atualização aplicada com sucesso (${data.aplicados} arquivos).`;
            showToast(msg, "success");
            addNotification(msg, "success");
        } else {
            const qtd = (data.falhas || []).length;
            const lista = (data.falhas || []).map(f => f.arquivo).slice(0, 5).join(", ");
            const msg = data.erro_geral
                ? `A atualização falhou: ${data.erro_geral}. Reaplique o pacote ou instale manualmente.`
                : `Atenção: a atualização não trocou ${qtd} arquivo(s) (${lista}${qtd > 5 ? '...' : ''}). ` +
                  `O sistema pode ficar instável — rode a atualização novamente ou aplique o pacote manualmente.`;
            showToast(msg, "error");
            addNotification(msg, "error");
        }
    } catch (e) {
        // Falha ao checar o resultado não deve atrapalhar o carregamento do app
        console.warn("Não foi possível verificar o resultado da atualização:", e);
    }
}

function initTableResizable() {
    const table = document.querySelector("#view-notas table");
    if (!table) return;
    
    const cols = table.querySelectorAll("thead tr:first-child th");
    const colGroupCols = table.querySelectorAll("colgroup col");
    
    cols.forEach((col, index) => {
        // Ignorar coluna de checkbox (índice 0) e coluna de ações (último índice)
        if (index === 0 || index === cols.length - 1) return;
        
        // Evitar adicionar múltiplos resizers
        if (col.querySelector(".resizer")) return;
        
        const resizer = document.createElement("div");
        resizer.className = "resizer";
        col.appendChild(resizer);
        
        // Passar a coluna do colgroup correspondente
        const colElement = colGroupCols[index];
        createResizableColumn(col, resizer, table, colElement);
    });
}

function createResizableColumn(col, resizer, table, colElement) {
    let x = 0;
    let w = 0;
    let tableWidth = 0;
    
    const mouseDownHandler = function(e) {
        e.preventDefault(); // Prevenir comportamento padrão do navegador
        e.stopPropagation(); // Evitar propagação para o cabeçalho th (não disparar ordenação)
        x = e.clientX;
        
        // Medimos o tamanho real visível da coluna e da tabela no layout
        w = col.offsetWidth;
        tableWidth = table.offsetWidth;
        
        resizer.classList.add("resizing");
        
        document.addEventListener('mousemove', mouseMoveHandler);
        document.addEventListener('mouseup', mouseUpHandler);
        
        // Prevenir seleção de texto durante o arraste
        document.body.style.userSelect = 'none';
        document.body.style.cursor = 'col-resize';
    };
    
    const mouseMoveHandler = function(e) {
        const dx = e.clientX - x;
        const newWidth = Math.max(w + dx, 50); // largura mínima de 50px
        const widthDiff = newWidth - w;
        
        // Ajustamos a largura total da tabela para acomodar a variação de tamanho da coluna!
        // Isso evita que o layout fique travado no tamanho da tela e permite a rolagem horizontal
        table.style.width = `${tableWidth + widthDiff}px`;
        
        // Se houver elemento <col>, alteramos a largura dele (o que atualiza a tabela inteira nativamente)
        if (colElement) {
            colElement.style.width = `${newWidth}px`;
            colElement.width = newWidth;
        } else {
            // Fallback caso não encontre <col>
            col.style.width = `${newWidth}px`;
            const filterCols = table.querySelectorAll("thead tr:last-child th");
            const index = Array.from(col.parentNode.children).indexOf(col);
            if (filterCols[index]) {
                filterCols[index].style.width = `${newWidth}px`;
            }
        }
    };
    
    const mouseUpHandler = function() {
        resizer.classList.remove("resizing");
        document.removeEventListener('mousemove', mouseMoveHandler);
        document.removeEventListener('mouseup', mouseUpHandler);
        
        document.body.style.userSelect = '';
        document.body.style.cursor = '';
    };
    
    resizer.addEventListener('mousedown', mouseDownHandler);
    
    // Bloquear cliques de ordenação quando o usuário clica ou solta o mouse no resizer
    resizer.addEventListener('click', function(e) {
        e.stopPropagation();
        e.preventDefault();
    });
}


// ==========================================================================
// 16. CENTRAL DE NOTIFICAÇÕES (M3 NOTIFICATION CENTER)
// ==========================================================================

function addNotification(mensagem, tipo = 'info') {
    const data = new Date();
    const hora = data.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
    
    const notification = {
        id: Date.now() + Math.random(),
        mensagem,
        tipo,
        hora,
        lida: false
    };
    
    AppState.notifications.unshift(notification); // Adiciona no início da lista (mais recentes primeiro)
    AppState.unreadNotificationsCount++;
    
    renderNotifications();
    
    // Animação sutil de jiggle/balanço no sino de notificação para dar feedback visual premium
    const bellBtn = document.getElementById("btn-notifications");
    if (bellBtn) {
        bellBtn.classList.remove("animate-wiggle");
        void bellBtn.offsetWidth; // Forçar reflow para reiniciar animação
        bellBtn.classList.add("animate-wiggle");
        setTimeout(() => bellBtn.classList.remove("animate-wiggle"), 800);
    }
}

function renderNotifications() {
    const badge = document.getElementById("notification-badge");
    const list = document.getElementById("notifications-list");
    
    if (badge) {
        const count = AppState.unreadNotificationsCount;
        badge.innerText = count;
        if (count > 0) {
            badge.classList.remove("hidden");
        } else {
            badge.classList.add("hidden");
        }
    }
    
    if (!list) return;
    
    if (AppState.notifications.length === 0) {
        list.innerHTML = `<p class="text-[11px] text-on-surface-variant text-center py-8">Nenhuma notificação encontrada.</p>`;
        return;
    }
    
    list.innerHTML = "";
    AppState.notifications.forEach(notif => {
        const item = document.createElement("div");
        // Estilização M3 para itens de notificação com background sutil de acordo com a leitura (sem reduzir opacidade do container!)
        if (!notif.lida) {
            item.className = "p-3 rounded-xl flex items-start gap-2.5 transition-all text-xs border border-primary/20 dark:border-primary-fixed-dim/30 bg-primary/8 dark:bg-primary/15 font-medium hover:bg-primary/12 dark:hover:bg-primary/25";
        } else {
            item.className = "p-3 rounded-xl flex items-start gap-2.5 transition-all text-xs border border-border/10 dark:border-border/5 bg-surface-container-lowest/50 dark:bg-surface-container-lowest/20 hover:bg-surface-container-high dark:hover:bg-surface-container-high/50";
        }
        
        let iconName = "info";
        let iconColor = "text-primary dark:text-sky-400";
        if (notif.tipo === 'success') {
            iconName = "check_circle";
            iconColor = "text-success dark:text-green-400";
        } else if (notif.tipo === 'warning') {
            iconName = "warning";
            iconColor = "text-warning dark:text-amber-400";
        } else if (notif.tipo === 'error') {
            iconName = "error";
            iconColor = "text-error dark:text-red-400";
        }
        
        // Let's use high-contrast text-on-surface and make unread text bold, read text normal
        const textWeightClass = !notif.lida ? "font-bold text-on-surface" : "text-on-surface-variant opacity-90";
        const timeColorClass = !notif.lida ? "text-primary font-semibold dark:text-primary-fixed-dim" : "text-on-surface-variant opacity-70";
        
        item.innerHTML = `
            <span class="material-symbols-outlined text-[18px] ${iconColor} mt-0.5">${iconName}</span>
            <div class="flex-1">
                <p class="text-[11px] ${textWeightClass} leading-tight">${notif.mensagem}</p>
                <span class="text-[9px] ${timeColorClass} mt-1 block">${notif.hora}</span>
            </div>
        `;
        list.appendChild(item);
    });
}

function toggleNotificationsMenu(event) {
    if (event) {
        event.stopPropagation();
        event.preventDefault();
    }
    
    const menu = document.getElementById("notifications-menu");
    if (!menu) return;
    
    const isHidden = menu.classList.contains("hidden");
    
    if (isHidden) {
        menu.classList.remove("hidden");
        // Marcar todas como lidas ao abrir a central
        AppState.unreadNotificationsCount = 0;
        AppState.notifications.forEach(notif => notif.lida = true);
        renderNotifications();
    } else {
        menu.classList.add("hidden");
    }
}

function limparNotificacoes(event) {
    if (event) {
        event.stopPropagation();
        event.preventDefault();
    }
    
    AppState.notifications = [];
    AppState.unreadNotificationsCount = 0;
    renderNotifications();
    showToast("Todas as notificações foram limpas", "info");
}

// Fechar menu de notificações ao clicar fora
document.addEventListener("click", (event) => {
    const menu = document.getElementById("notifications-menu");
    const btn = document.getElementById("btn-notifications");
    
    if (menu && !menu.classList.contains("hidden")) {
        if (!menu.contains(event.target) && !btn.contains(event.target)) {
            menu.classList.add("hidden");
        }
    }
});


