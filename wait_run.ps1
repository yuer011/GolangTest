<#
.SYNOPSIS
    监听 run_case.ps1 启动的独立窗口，run 结束后返回，并默认自动关闭该窗口（替代盲等 sleep）。

.WHY
    run_case.ps1 用 Start-Process 新开窗口跑 run 后立即返回，本终端不知道何时结束。
    盲等固定秒数不优雅（早结束白等、慢了又不够）。本脚本以「日志写出结尾汇总」为主判据、
    以「python 子进程消失」为兜底判据，run 一结束就返回，并默认关闭那个运行窗口
    （日志已完整落盘、窗口无需保留；-KeepWindow 可保留用于排查）。
    纯只读监听，不启动任何 run，AI 助手重复调用也无副作用（不会像 launch 那样双发）。

.PARAMETER TimeoutSec  最长等待秒数（兜底）。默认 300。
.PARAMETER PollSec     轮询间隔秒数。默认 3。
.PARAMETER KeepWindow  带上则跑完不关闭运行窗口（默认自动关闭）。

.EXAMPLE
    .\scripts\wait_run.ps1
    .\scripts\wait_run.ps1 -KeepWindow
#>
param(
    [int]$TimeoutSec = 300,
    [int]$PollSec = 3,
    [switch]$KeepWindow
)

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PidFile = Join-Path $ProjectRoot ".tmp\last_run_win.pid"

if (-not (Test-Path $PidFile)) {
    Write-Error "找不到 $PidFile —— 请先用 run_case.ps1 启动一个 case。"
    exit 1
}

$winPid = [int](Get-Content $PidFile -Raw).Trim()
# 本次启动时刻：用 pid 文件写入时间做基准，只认「本次」启动之后的日志，避免读到旧日志误判
$LaunchTime = (Get-Item $PidFile).LastWriteTime
$LogDir = Join-Path $ProjectRoot "logs"

Write-Host "监听窗口 PID=$winPid 的 run（日志为主、进程为辅）..." -ForegroundColor Cyan

# 取当前所有「正在执行 dlp_auto.run 的 python 进程」PID（全局，只读查询）。
# 不按 ParentProcessId 盯 pid 文件那一个窗口——双发时 pid 文件记的可能是「被锁拦、
# python 瞬间就退出」的空壳窗口，盯它永远看不到 run 在跑。改按命令行特征全局找，
# 才能真实反映「有没有 run 在执行」。
function Get-RunChildren {
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*dlp_auto.run*" } |
        Select-Object -ExpandProperty ProcessId
}

# 枚举「所有 run_case.ps1 起的运行窗口」：命令行含 dlp_auto.run 的 powershell。
# 为什么不只认 pid 文件里那一个——真机 GUI run 可能被调用层双发（起两个窗口），
# pid 文件只留最后写入的一个；被锁拦的那个会自己 exit，正常跑完的那个却因 -NoExit
# 留在屏上无人关。故收尾时按命令行特征找出所有运行窗口，把「其下已无 python 子进程」
# （= 已跑完 / 已被锁拦退出）的统一关掉，避免残留（见 LESSONS.md 双发相关）。
function Get-AllRunWindows {
    Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*dlp_auto.run*" } |
        Select-Object -ExpandProperty ProcessId
}

function Test-ProcHasPythonChild([int]$procId) {
    [bool](Get-CimInstance Win32_Process -Filter "ParentProcessId=$procId" -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "python*" })
}

# 最新日志是否已写出结尾汇总（且该日志确属本次运行）
function Test-RunDone {
    $latest = Get-ChildItem (Join-Path $LogDir "run_*.log") -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime | Select-Object -Last 1
    if (-not $latest) { return $false }
    # 只认「本次启动之后写入」的日志：旧 run 的日志在本次启动前就已完成
    # （LastWriteTime < LaunchTime），必被排除；唯有当前 run 跑完写出汇总时其
    # LastWriteTime 才 >= LaunchTime。严格用 >= LaunchTime（不留余量）——否则
    # 「刚结束不久的上一次 run 日志」会被误当成本次完成，导致过早判定/关掉在跑的窗口。
    if ($latest.LastWriteTime -lt $LaunchTime) { return $false }
    $tail = Get-Content $latest.FullName -Tail 3 -ErrorAction SilentlyContinue
    return [bool]($tail | Select-String -SimpleMatch "total_tokens")
}

$deadline = (Get-Date).AddSeconds($TimeoutSec)
$startWait = Get-Date
$seen = $false
$done = $false

while ((Get-Date) -lt $deadline) {
    $children = @(Get-RunChildren)
    if ($children.Count -gt 0) {
        if (-not $seen) {
            $seen = $true
            Write-Host "  run 已启动（python PID: $($children -join ', ')），等待其结束..." -ForegroundColor DarkGray
        }
    }
    elseif ($seen) { $done = $true; break }                  # run 曾在跑、现已全部结束

    # 日志判据只在「确认 run 真的跑起来过」之后才生效：否则 wait_run 刚启动那一刻，
    # 可能读到上一次 run 的旧日志（尾部已有 total_tokens、时间又≥本次基准）而 0s 误判。
    # 必须先 $seen（看到本次 run 的 python 进程），再认「日志写完汇总」= 本次结束。
    if ($seen -and (Test-RunDone)) { $done = $true; break }

    Start-Sleep -Seconds $PollSec
}

$elapsed = [int]((Get-Date) - $startWait).TotalSeconds
if ($done) {
    Write-Host "✅ run 已结束（监听耗时约 ${elapsed}s）" -ForegroundColor Green
} else {
    Write-Host "⚠️ 达到超时上限 ${TimeoutSec}s（run 可能仍在跑，请看运行窗口）" -ForegroundColor Yellow
}

# 打印最新日志名，方便直接查看
$latest = Get-ChildItem (Join-Path $LogDir "run_*.log") -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime | Select-Object -Last 1
if ($latest) { Write-Host "最新日志：logs\$($latest.Name)" -ForegroundColor Cyan }

# 默认自动关闭运行窗口（日志已完整；带 -KeepWindow 则保留）。
# 关「所有已跑完/已退出」的 run 窗口，而非仅 pid 文件那一个——覆盖双发起了两个窗口
# 的情况：其下已无 python 子进程的窗口都属于已结束，统一关掉；仍有 python 在跑的
# 窗口（极少数并行场景）则保留，绝不误杀正在执行的 run。
if ($done -and -not $KeepWindow) {
    $closed = 0
    foreach ($p in @(Get-AllRunWindows)) {
        if (Test-ProcHasPythonChild $p) { continue }   # 还在跑，保留
        Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
        $closed++
    }
    if ($closed -gt 0) {
        Write-Host "🧹 已自动关闭 $closed 个已结束的运行窗口" -ForegroundColor DarkGray
    }
}
