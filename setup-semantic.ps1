$ErrorActionPreference='Stop'
$kaltsitSemanticRoot=$PSScriptRoot
Set-Location -LiteralPath $kaltsitSemanticRoot
$env:PYTHONUTF8='1'
$kaltsitBasePython=Join-Path $kaltsitSemanticRoot '.venv\Scripts\python.exe'
if(-not(Test-Path -LiteralPath $kaltsitBasePython)){throw '请先完成01-安装依赖.cmd，再安装可选的本地语义检索'}
$kaltsitSemanticPython=Join-Path $kaltsitSemanticRoot '.semantic-venv\Scripts\python.exe'
if(-not(Test-Path -LiteralPath $kaltsitSemanticPython)){
    & $kaltsitBasePython -m venv (Join-Path $kaltsitSemanticRoot '.semantic-venv')
    if($LASTEXITCODE -ne 0){throw '语义检索独立环境创建失败'}
}
& $kaltsitSemanticPython -m pip install -r (Join-Path $kaltsitSemanticRoot 'requirements-semantic.txt')
if($LASTEXITCODE -ne 0){throw '可选依赖安装失败，原有关键词检索仍可使用'}
& $kaltsitSemanticPython (Join-Path $kaltsitSemanticRoot 'scripts\build_semantic_index.py') --allow-download
if($LASTEXITCODE -ne 0){throw '模型下载或索引创建失败，原有关键词检索仍可使用；网络恢复后可重试'}
Write-Host '本地语义检索准备完成。重新启动本副本的机器人或测试窗口后启用'
Write-Host '没有登录QQ、启动群回复或调用Luna；没有修改Codex配置'
