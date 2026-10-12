param([switch]$InstallPrerequisites)
$ErrorActionPreference='Stop'
$kaltsitSourceRoot=$PSScriptRoot
Set-Location -LiteralPath $kaltsitSourceRoot
if($InstallPrerequisites){
    if(-not(Get-Command winget -ErrorAction SilentlyContinue)){throw '未找到winget，请自行安装Python 3.13 x64和Node.js LTS'}
    if(-not(Get-Command py -ErrorAction SilentlyContinue)){
        & winget install --id Python.Python.3.13 --exact --source winget
        if($LASTEXITCODE -ne 0){throw 'Python安装未完成'}
    }
    if(-not(Get-Command node -ErrorAction SilentlyContinue)){
        & winget install --id OpenJS.NodeJS.LTS --exact --source winget
        if($LASTEXITCODE -ne 0){throw 'Node.js安装未完成'}
    }
    $env:Path=[Environment]::GetEnvironmentVariable('Path','Machine')+';'+[Environment]::GetEnvironmentVariable('Path','User')
}
if(-not(Get-Command py -ErrorAction SilentlyContinue)){throw '需要Python 3.13 x64。安装后重开本窗口，或执行 setup.ps1 -InstallPrerequisites'}
$kaltsitPythonVersion='-3.13'
$kaltsitPythonVersionOk=$false
try { & py -3.13 -c 'import sys; assert sys.maxsize>2**32' 2>$null; $kaltsitPythonVersionOk=($LASTEXITCODE -eq 0) } catch {}
if(-not $kaltsitPythonVersionOk){
    $kaltsitPythonVersion='-3.12'
    try { & py -3.12 -c 'import sys; assert sys.maxsize>2**32' 2>$null; $kaltsitPythonVersionOk=($LASTEXITCODE -eq 0) } catch {}
    if(-not $kaltsitPythonVersionOk){throw '需要64位Python 3.12或3.13'}
}
if(-not(Get-Command node -ErrorAction SilentlyContinue)){throw '需要Node.js LTS（用于工具安全Hook）'}
if(-not(Test-Path -LiteralPath (Join-Path $kaltsitSourceRoot '.venv\Scripts\python.exe'))){
    & py $kaltsitPythonVersion -m venv .venv
    if($LASTEXITCODE -ne 0){throw '虚拟环境创建失败'}
}
$kaltsitPython=Join-Path $kaltsitSourceRoot '.venv\Scripts\python.exe'
& $kaltsitPython -m pip install -r (Join-Path $kaltsitSourceRoot 'requirements.txt')
if($LASTEXITCODE -ne 0){throw '依赖安装失败，请检查网络后重试'}
if(-not(Get-Command codex -ErrorAction SilentlyContinue)){
    Write-Host '安装OpenAI官方Codex CLI；保留现有CLI时不会自动升级'
    & npm.cmd install -g @openai/codex
    if($LASTEXITCODE -ne 0){throw 'Codex CLI安装未完成'}
}
Write-Host '依赖已准备。请执行 codex login 登录自己的账号，然后按README接入OneBot，运行02-配置机器人.cmd'
Write-Host '此脚本未登录账号、创建群授权或启动回复；没有修改Codex全局配置'
