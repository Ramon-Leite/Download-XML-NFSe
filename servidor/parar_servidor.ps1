# ============================================================
#  Identifica e para os processos do servidor NFSe desta instalacao.
#  Chamado por parar_servidor.bat e por atualizar.bat.
#
#  Por que existe: o "schtasks /end" encerra apenas o processo de topo da
#  tarefa (o cmd do iniciar_servidor.bat). O Python que ele lancou sobrevive
#  como orfao e continua segurando a porta.
#
#  E por que NAO usar "taskkill /F /IM pythonw.exe": aquilo mata todo Python
#  sem console da maquina, inclusive de outros sistemas que rodem no mesmo
#  servidor. Em 13/08/2026 isso derrubou outros programas do escritorio.
#
#  Um processo so entra na mira se atender um destes criterios:
#    a) o executavel ou a linha de comando apontam para ESTA instalacao
#       (no servidor o .venv fica dentro da pasta do projeto);
#    b) e um processo Python escutando a porta do sistema -- necessario
#       porque com o Python do sistema, e nao o do venv, o caminho do
#       projeto nao aparece na linha de comando, so no diretorio de
#       trabalho, que o Windows nao expoe;
#    c) e um filho Python de alguem ja identificado por (a) ou (b), que
#       sobreviveria ao pai segurando recursos.
#
#  Parametros (sem nenhum, para de verdade):
#    -Listar   mostra os alvos sem encerrar nada
#    -Contar   imprime so a quantidade, para scripts
#    -Porta    porta do sistema (padrao 8000)
# ============================================================
param(
    [switch]$Listar,
    [switch]$Contar,
    [int]$Porta = 8000
)

$raiz = (Resolve-Path (Split-Path -Parent $PSScriptRoot)).Path

# (a) processos cujo executavel/linha de comando sao desta pasta
$daPasta = @(Get-CimInstance Win32_Process).Where({
    $_.Name -like 'python*.exe' -and (
        ($_.ExecutablePath -and $_.ExecutablePath.StartsWith($raiz, [StringComparison]::OrdinalIgnoreCase)) -or
        ($_.CommandLine -and $_.CommandLine -like ('*' + $raiz + '*'))
    )
})

# (b) quem escuta a porta, se for Python
$daPorta = @()
$pidsPorta = @(Get-NetTCPConnection -LocalPort $Porta -State Listen -ErrorAction SilentlyContinue).ForEach({ $_.OwningProcess })
foreach ($processId in ($pidsPorta | Select-Object -Unique)) {
    $p = Get-CimInstance Win32_Process -Filter "ProcessId=$processId" -ErrorAction SilentlyContinue
    if ($p -and $p.Name -like 'python*.exe') { $daPorta += $p }
}

# O @() externo e necessario: com um unico resultado o Sort-Object devolve o
# objeto solto, sem .Count, e a contagem sairia vazia.
$alvos = @(@($daPasta + $daPorta) | Sort-Object ProcessId -Unique)

# (c) filhos Python dos alvos
if ($alvos.Count -gt 0) {
    $idsAlvo = $alvos.ForEach({ $_.ProcessId })
    $filhos = @(Get-CimInstance Win32_Process).Where({
        $_.Name -like 'python*.exe' -and
        $idsAlvo -contains $_.ParentProcessId -and
        $idsAlvo -notcontains $_.ProcessId
    })
    $alvos = @(@($alvos + $filhos) | Sort-Object ProcessId -Unique)
}

# Modo contagem: quantos servidores estao NO AR, ou seja, escutando a porta.
# De proposito nao conta $alvos: ali entram tambem processos-filho, que sao
# normais e fariam o atualizar.bat dar alarme falso. O que quebra o sistema e
# dois processos atendendo a mesma porta -- no Windows isso e possivel e foi o
# que aconteceu em 13/08/2026, com o orfao respondendo no lugar do novo.
if ($Contar) {
    Write-Output @($daPorta).Count
    return
}

if ($alvos.Count -eq 0) {
    if (-not $Listar) {
        Write-Host 'Parando a tarefa agendada...'
        schtasks /end /tn "NFSe Servidor" 2>&1 | Out-Null
    }
    Write-Host '  Nenhum processo do sistema encontrado (ja estava parado).' -ForegroundColor Yellow
    return
}

Write-Host ("  {0} processo(s) desta instalacao:" -f $alvos.Count)
foreach ($p in $alvos) {
    Write-Host ('    PID {0}  {1}' -f $p.ProcessId, $p.Name)
}

if ($Listar) {
    Write-Host ''
    Write-Host 'Simulacao: nada foi encerrado.' -ForegroundColor Cyan
    return
}

Write-Host 'Parando a tarefa agendada...'
schtasks /end /tn "NFSe Servidor" 2>&1 | Out-Null

foreach ($p in $alvos) {
    try {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
        Write-Host ('    encerrado PID {0}' -f $p.ProcessId) -ForegroundColor Green
    } catch {
        Write-Host ('    NAO foi possivel encerrar o PID {0}: {1}' -f $p.ProcessId, $_.Exception.Message) -ForegroundColor Red
    }
}

Start-Sleep -Seconds 2
Write-Host 'Servidor parado.' -ForegroundColor Green
