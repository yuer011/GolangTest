<#
.SYNOPSIS
    清理本地运行产物（日志 / 调试截图 / 报告等），把磁盘占用降下来。

.WHY
    真机 GUI run 会持续往 logs/、screenshots/（--debug-shots）、reports/、.tmp/
    落盘产物，跑多了会堆积。按 AGENTS.md §3「清理走独立脚本手动执行、不接线到 run
    热路径」，把清理沉淀成这个可复用脚本，而不是每次手敲 rm。

    默认「只看不删」（预览），确认无误再加 -Confirm 真删；且默认只清 logs、
    并保留最近若干条，避免误删正在排查的现场。.tmp 默认永不触碰（除非显式 -IncludeTmp），
    因为里面常有 reflect_report.md、last_run_win.pid 等还想留着的东西。

    两种清理粒度：
    - -Target：按「文件」清理某目录顶层的文件（logs / reports / screenshots 的 step_*.png）。
    - -DirTarget：按「子目录」清理，保留最近 N 个子目录。用于 screenshots/final 这类
      「每次 run 一个 run_id 子目录」的结构——保留最近 N 次 run 的整个目录。
    两者可同时给，各按各的规则跑；KeepRecent / Days / Confirm 共用。

.PARAMETER Target
    按文件清理的产物目录，可多选。默认仅 logs。可选 logs / screenshots / reports。
    .tmp 不在此列——它只受 -IncludeTmp 控制（默认不动）。

.PARAMETER DirTarget
    按子目录清理的目录（相对项目根的路径），可多选。默认空。
    例：screenshots/final —— 按 run_id 子目录保留最近 N 个。

.PARAMETER KeepRecent
    按修改时间保留最近 N 个（文件或子目录，默认 3）。设 0 表示不保留、全清。
    与 -Days 同时给时，两个条件都要满足才删（既够旧、又不在最近 N 个内）。

.PARAMETER Days
    只清理「N 天前」的项（早于 now-N 天）。默认 0 = 不按龄过滤。

.PARAMETER IncludeTmp
    额外把 .tmp/ 也纳入按文件清理（默认不动 .tmp）。谨慎使用。

.PARAMETER Confirm
    真正执行删除。不带时为「预览模式」，只打印将删哪些项、不实际删除。

.EXAMPLE
    # 预览：清 logs、保留最近 3 条（默认，不会真删）
    .\scripts\clean_artifacts.ps1

.EXAMPLE
    # 真删：清 reports 文件 + screenshots/final 子目录，各保留最近 3 个
    .\scripts\clean_artifacts.ps1 -Target reports -DirTarget screenshots/final -Confirm

.EXAMPLE
    # 清 logs + screenshots 顶层文件，只删 3 天前的，各保留最近 5 个，先预览
    .\scripts\clean_artifacts.ps1 -Target logs,screenshots -Days 3 -KeepRecent 5

.NOTES
    - 所有目标目录都在 .gitignore 内，清理不影响 git 跟踪的源码。
    - -Target 只删文件、不删目录本身；-DirTarget 删整个子目录（含其内文件）。
    - 目标目录本身清空后仍保留，下次 run 直接复用。
    - 项目根按脚本自身位置推导，不写死绝对路径（换机器也能用）。
#>
param(
    [ValidateSet("logs", "screenshots", "reports")]
    [string[]]$Target = @("logs"),

    [string[]]$DirTarget = @(),

    [int]$KeepRecent = 3,

    [int]$Days = 0,

    [switch]$IncludeTmp,

    [switch]$Confirm
)

# 项目根 = 本脚本所在目录(scripts)的上一级
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$cutoff = if ($Days -gt 0) { (Get-Date).AddDays(-$Days) } else { $null }

$script:totalDel = 0
$script:totalBytes = 0L

# 统一的「按修改时间新→旧、跳过最近 KeepRecent 个、再按 -Days 过滤」候选筛选。
# $items 可为文件或目录对象；$sizeOf 负责算单项占用（目录要递归求和）。
function Invoke-Clean {
    param(
        [string]$Label,          # 打印用标签
        [object[]]$Items,        # 待筛选的文件/目录对象
        [string]$Kind,           # "文件" / "子目录"
        [scriptblock]$SizeOf     # 单项字节数计算
    )
    $sorted = @($Items | Sort-Object LastWriteTime -Descending)
    $candidates = if ($KeepRecent -gt 0) { $sorted | Select-Object -Skip $KeepRecent } else { $sorted }
    if ($cutoff) { $candidates = $candidates | Where-Object { $_.LastWriteTime -lt $cutoff } }
    $candidates = @($candidates)

    if ($candidates.Count -eq 0) {
        Write-Host "  [$Label] 无可清理$Kind（共 $($sorted.Count) 个，均在保留范围内）" -ForegroundColor Green
        return
    }

    $bytes = 0L
    foreach ($c in $candidates) { $bytes += (& $SizeOf $c) }
    Write-Host "  [$Label] 将清理 $($candidates.Count) 个$Kind（$([math]::Round($bytes/1MB,2)) MB），保留 $([math]::Min($KeepRecent,$sorted.Count)) 个最近的" -ForegroundColor Yellow
    foreach ($c in $candidates) {
        if ($Confirm) {
            Remove-Item $c.FullName -Recurse -Force -ErrorAction SilentlyContinue
            Write-Host "    - 删除 $($c.Name)" -ForegroundColor DarkGray
        }
        else {
            Write-Host "    - [预览] $($c.Name)  ($($c.LastWriteTime.ToString('MM-dd HH:mm')))" -ForegroundColor DarkGray
        }
    }
    $script:totalDel += $candidates.Count
    $script:totalBytes += $bytes
}

$mode = if ($Confirm) { "删除" } else { "预览（不删，加 -Confirm 才真删）" }
Write-Host "== 清理产物 [$mode] ==" -ForegroundColor Cyan
Write-Host "  按文件: $($Target -join ', ')  按子目录: $(if ($DirTarget) { $DirTarget -join ', ' } else { '无' })  保留最近: $KeepRecent  按龄: $(if ($cutoff) { "$Days 天前" } else { '不限' })" -ForegroundColor DarkGray

# ── 按文件清理：Target + 可选 .tmp ──────────────────────────────────
$fileDirs = [System.Collections.Generic.List[string]]::new()
foreach ($t in $Target) { $fileDirs.Add($t) }
if ($IncludeTmp -and ($fileDirs -notcontains ".tmp")) { $fileDirs.Add(".tmp") }

foreach ($d in $fileDirs) {
    $full = Join-Path $ProjectRoot $d
    if (-not (Test-Path $full)) { Write-Host "  [$d] 不存在，跳过" -ForegroundColor DarkGray; continue }
    $files = Get-ChildItem $full -File -ErrorAction SilentlyContinue
    Invoke-Clean -Label $d -Items $files -Kind "文件" -SizeOf { param($f) [long]$f.Length }
}

# ── 按子目录清理：DirTarget（如 screenshots/final）─────────────────
foreach ($d in $DirTarget) {
    $full = Join-Path $ProjectRoot $d
    if (-not (Test-Path $full)) { Write-Host "  [$d] 不存在，跳过" -ForegroundColor DarkGray; continue }
    $subdirs = Get-ChildItem $full -Directory -ErrorAction SilentlyContinue
    Invoke-Clean -Label $d -Items $subdirs -Kind "子目录" -SizeOf {
        param($dir) [long]((Get-ChildItem $dir.FullName -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum)
    }
}

$verb = if ($Confirm) { "已清理" } else { "将清理" }
Write-Host "== $verb $script:totalDel 项，约 $([math]::Round($script:totalBytes/1MB,2)) MB ==" -ForegroundColor Cyan
if (-not $Confirm -and $script:totalDel -gt 0) {
    Write-Host "（这是预览。确认无误后加 -Confirm 真正删除。）" -ForegroundColor Yellow
}
