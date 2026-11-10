<#
.SYNOPSIS
    在「独立的 PowerShell 窗口」里运行一个 DLP 自动化 case，脱离 AI 助手沙箱。

.WHY
    AI 助手通过内置 Shell 工具直接跑 `run` 时，会等命令返回（真机 GUI case 约需
    50~120 秒）；执行层等不到响应会自动重试，从而发起「第二个 run 进程」——即所谓
    双发（详见 LESSONS.md #5）。本脚本用 Start-Process 新开一个独立窗口来跑 run，
    AI 助手侧毫秒级返回、不再触发重试；真正的 GUI run 在外部窗口里独立进行，彻底
    脱离沙箱。配合 dlp_auto/core/runlock.py 的单实例锁形成双保险。

.PARAMETER Filter
    传给 `run --filter` 的 case.id 子串。例：qq.outbound_file.upload

.PARAMETER DebugShots
    可选。带上则附加 --debug-shots，把每步截图落盘到 screenshots/（失败时看现场用）。

.PARAMETER LarkBase
    可选。带上则附加 --lark-base，跑完把结果 + 末步截图同步到飞书多维表格
    （需本机已 `lark-cli auth login`）。Windows 上 lark-cli 是 lark-cli.cmd，
    已在 report/lark_base_hook.py 里按平台解析，无需额外处理。

.PARAMETER Policy
    可选。传给 `run --policy` 的预期策略（audit / block）。传了即自动启用
    DLP 客户端日志验证（无需再加 --check-log）；不传则 policy=none、不验证日志。

.PARAMETER CheckServer
    可选。带上则附加 --check-server，启用服务端事件回查（run 级，所有 case 跑完后按
    事件ID统一查一次）。**需配合 -Policy audit/block**（回查依赖本地日志解析出的事件ID）；
    config verify.server.mock=true 时只验证链路、恒记未判定。

.EXAMPLE
    .\scripts\run_case.ps1 -Filter qq.outbound_file.upload
    .\scripts\run_case.ps1 -Filter qq.outbound_file.copy_paste -DebugShots
    .\scripts\run_case.ps1 -Filter qq.outbound_file.drag_drop -LarkBase
    .\scripts\run_case.ps1 -Filter qq.outbound_file.upload -Policy audit
    .\scripts\run_case.ps1 -Filter qq.outbound_file.upload -Policy audit -CheckServer

.NOTES
    - 新窗口用 -NoExit 保持打开，跑完输出留在屏上，方便查看/复制。
    - python 与项目根均按脚本自身位置推导，不写死绝对路径（换机器也能用）。
    - 用 -WorkingDirectory 切目录 + 极简 -Command，避免复杂字符串拼接出错。
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$Filter,

    [switch]$DebugShots,

    [switch]$LarkBase,

    [ValidateSet("audit", "block")]
    [string]$Policy,

    [switch]$CheckServer
)

# 项目根 = 本脚本所在目录(scripts)的上一级
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Error "找不到虚拟环境 python：$Python`n请先在项目根创建 .venv 并安装依赖。"
    exit 1
}

# WeLink 组尾会完全退出，下一次必须冷启动。真机确认：必须由调用本脚本的父 PowerShell
# 直接 Start-Process -PassThru，并保持父进程至少 4 秒；从 case Python 或新窗口中的嵌套
# PowerShell 启动都会立即退出。4 秒后先确认启动进程仍存活，再创建独立 run 窗口。
if ($Filter -match '(^|\.)welink(\.|$)') {
    $WeLinkExe = (& $Python -c "from dlp_auto.actions._windows.apps import _resolve_exe; print(_resolve_exe('welink'))" |
        Select-Object -Last 1).Trim()
    if (-not $WeLinkExe -or -not (Test-Path -LiteralPath $WeLinkExe)) {
        Write-Error "无法解析 WeLink.exe，停止运行：$WeLinkExe"
        exit 1
    }
    $WeLinkDir = Split-Path -Parent $WeLinkExe
    $WeLinkProcess = Start-Process -FilePath $WeLinkExe -WorkingDirectory $WeLinkDir -PassThru
    Start-Sleep -Seconds 4
    $WeLinkProcess.Refresh()
    if ($WeLinkProcess.HasExited) {
        Write-Error "WeLink 冷启动进程已提前退出（exit=$($WeLinkProcess.ExitCode)），停止运行 case。"
        exit 1
    }
}

# 新窗口里要执行的那一句命令：& '<python>' -m dlp_auto.run run --filter <x> [--debug-shots] [--lark-base]
$command = "& '$Python' -m dlp_auto.run run --filter $Filter"
if ($DebugShots) { $command += " --debug-shots" }
if ($LarkBase) { $command += " --lark-base" }
if ($Policy) { $command += " --policy $Policy" }
if ($CheckServer) { $command += " --check-server" }
# 双发防呆的收尾：若本窗口的 run 因抢不到单实例锁而空跑（run.py 退出码 3），
# 就让本窗口自动关闭，不给用户留「已有 run 在跑」的僵尸窗口；正常完成(0)/失败(1)/
# 配置无效(2) 时不退出，靠 -NoExit 保留窗口与输出供查看/wait_run.ps1 收尾。
# 追加句不含任何引号，避免跨进程传参时引号丢失导致新窗口 ParserError。
$command += " ; if (`$LASTEXITCODE -eq 3) { exit }"

# --lark-base 依赖本机 lark-cli（Windows 上是 %APPDATA%\npm\lark-cli.cmd）。
# 若本脚本从「PATH 里没有 npm/nodejs」的环境启动（如 AI 助手沙箱、精简终端），
# Start-Process 起的新窗口会继承那份残缺 PATH，导致 run 的 python 子进程
# shutil.which 找不到 lark-cli → 同步静默跳过。
# 修法：在【父进程本身】就把「机器级 + 用户级」持久化 PATH（一定含 Node 装的
# npm/nodejs 目录）重建到 $env:Path，Start-Process 会把父进程环境整体传给子进程，
# 于是新窗口天然拿到完整 PATH。全程不往 -Command 字符串里拼带引号的 .NET 调用，
# 规避跨进程传参时双引号丢失导致的语法崩溃（曾踩坑：GetEnvironmentVariable(Path,Machine)
# 引号被吞 → 新窗口一起来就 ParserError）。仅 --lark-base 时需要，不影响其它场景。
if ($LarkBase) {
    $machinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = ($machinePath, $userPath | Where-Object { $_ }) -join ';'
}

# Start-Process 立即返回（本终端不阻塞，故不触发 AI 执行层重试）；
# -WorkingDirectory 负责切到项目根；-NoExit 让新窗口跑完不自动关闭；
# -PassThru 拿到新窗口进程对象，记录其 PID 供 wait_run.ps1 监听。
$proc = Start-Process powershell -WorkingDirectory $ProjectRoot -PassThru -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy", "Bypass",
    "-Command", $command
)

# 记录新窗口 PID，供 wait_run.ps1 监听其 python 子进程判断 run 是否结束
$TmpDir = Join-Path $ProjectRoot ".tmp"
if (-not (Test-Path $TmpDir)) { New-Item -ItemType Directory -Path $TmpDir | Out-Null }
Set-Content -Path (Join-Path $TmpDir "last_run_win.pid") -Value $proc.Id -Encoding ASCII

Write-Host "已在新的 PowerShell 窗口启动 case：$Filter (窗口 PID=$($proc.Id))" -ForegroundColor Green
Write-Host "命令：$command" -ForegroundColor DarkGray
Write-Host "（本终端不等待；可运行 scripts\wait_run.ps1 监听结束，或到新窗口看进度）" -ForegroundColor DarkGray
