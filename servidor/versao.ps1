# ============================================================
#  Mostra a versao do sistema no servidor.
#  Chamado por versao.bat -- nao precisa rodar direto.
#
#  Responde tres perguntas que sao diferentes entre si:
#    1. Que codigo esta no disco?      (o commit)
#    2. Falta puxar algo do GitHub?
#    3. O processo no ar esta rodando ESSE codigo?
#
#  A pergunta 3 existe porque em 13/08/2026 o servidor ficou com o
#  codigo novo no disco e o antigo no ar: a tela atualizou (static/ e
#  lido do disco a cada requisicao) mas a API continuou respondendo pelo
#  processo velho, que sobrevivia ao "schtasks /end" como orfao.
# ============================================================

$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

Write-Host ''
Write-Host '=== CODIGO NO DISCO ===' -ForegroundColor Cyan
$commit = git log -1 --pretty=format:'%h|%s|%ad' --date=format:'%d/%m/%Y %H:%M' 2>$null
if ([string]::IsNullOrWhiteSpace($commit)) {
    Write-Host '  Nao foi possivel ler o git neste diretorio.' -ForegroundColor Red
} else {
    $partes = $commit -split '\|'
    Write-Host ('  Commit : {0}' -f $partes[0])
    Write-Host ('  Assunto: {0}' -f $partes[1])
    Write-Host ('  Data   : {0}' -f $partes[2])
}

Write-Host ''
Write-Host '=== COMPARADO AO GITHUB ===' -ForegroundColor Cyan
git fetch --quiet origin 2>$null
$atras = (git rev-list --count HEAD..origin/main 2>$null)
if ([string]::IsNullOrWhiteSpace($atras)) {
    Write-Host '  Nao deu para consultar o GitHub (sem rede?).' -ForegroundColor Yellow
} elseif ($atras -eq '0') {
    Write-Host '  Atualizado, nao ha commit novo no GitHub.' -ForegroundColor Green
} else {
    Write-Host ('  ATRASADO em {0} commit(s). Rode servidor\atualizar.bat' -f $atras) -ForegroundColor Yellow
}

Write-Host ''
Write-Host '=== PROCESSO NO AR ===' -ForegroundColor Cyan
$procs = @(Get-CimInstance Win32_Process).Where({
    $_.Name -like 'python*.exe' -and $_.CommandLine -like '*app.py*'
})

if ($procs.Count -eq 0) {
    Write-Host '  Nenhuma instancia rodando: o sistema esta FORA DO AR.' -ForegroundColor Red
    Write-Host '  Suba com: schtasks /run /tn "NFSe Servidor"' -ForegroundColor Yellow
} else {
    if ($procs.Count -gt 1) {
        Write-Host ('  ATENCAO: {0} instancias rodando, o esperado e 1.' -f $procs.Count) -ForegroundColor Red
        Write-Host '  Com mais de uma, a API pode responder pelo processo ANTIGO' -ForegroundColor Red
        Write-Host '  mesmo com o codigo novo no disco.' -ForegroundColor Red
    } else {
        Write-Host '  1 instancia rodando.' -ForegroundColor Green
    }

    # Arquivo .py mais recente do projeto (ignora venv e cache de bytecode)
    $maisNovo = @(Get-ChildItem -Path $raiz -Filter *.py -Recurse -ErrorAction SilentlyContinue).Where({
        $_.FullName -notlike '*\.venv\*' -and $_.FullName -notlike '*__pycache__*'
    }) | Sort-Object LastWriteTime -Descending | Select-Object -First 1

    foreach ($p in $procs) {
        Write-Host ('  PID {0}, no ar desde {1:dd/MM/yyyy HH:mm}' -f $p.ProcessId, $p.CreationDate)
        if ($maisNovo -and $maisNovo.LastWriteTime -gt $p.CreationDate) {
            Write-Host ('    RODANDO CODIGO ANTIGO: {0} mudou em {1:dd/MM/yyyy HH:mm},' -f $maisNovo.Name, $maisNovo.LastWriteTime) -ForegroundColor Red
            Write-Host '    depois deste processo subir. Reinicie para o codigo novo entrar.' -ForegroundColor Red
        } else {
            Write-Host '    Rodando o codigo que esta no disco.' -ForegroundColor Green
        }
    }
}

Write-Host ''
