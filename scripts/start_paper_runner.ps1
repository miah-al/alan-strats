# Starts the automated paper runner for one strategy. Schedule it on trading days at 10:30 ET, e.g.:
#   schtasks /Create /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 10:30 /TN "AlanTrader paper NDX" ^
#     /TR "powershell -NoProfile -ExecutionPolicy Bypass -File \"<this checkout>\scripts\start_paper_runner.ps1\""
# (adjust /ST to your machine's local time for 10:30 ET). The runner waits for 09:30 ET if started early,
# resumes a session after a crash or restart (paper_state/), and exits after 16:01 ET.
# Nothing here names a folder: the checkout is the one this script sits in, and the strategies are the sibling
# alan_trader_strategies beside it.
param(
    [string]$Strategy = "ndx_0dte_tasty",
    # default: this checkout's own venv, else the shared one
    [string]$Python = "",
    [int]$Poll = 15,
    # stream the legs' quotes over DXLink instead of polling REST (the clone's resting orders, 2026-10-06)
    [switch]$Stream,
    # shadow: the session runs with the ledger off (--no-ledger); its logs and state are kept, nothing is booked
    [switch]$NoLedger,
    # "key=value;key2=value2": the limits the trader set for this strategy (the service's app.TradeLimit), as --param
    [string]$Params = ""
)
$extra = @()
foreach ($kv in ($Params -split ';')) { if ($kv.Trim()) { $extra += '--param'; $extra += $kv.Trim() } }
if ($Stream) { $extra += '--stream' }
if ($NoLedger) { $extra += '--no-ledger' }
$env:PYTHONIOENCODING = "utf-8"
$repo = Split-Path -Parent $PSScriptRoot
$strategies = Join-Path (Split-Path -Parent $repo) "alan_trader_strategies"
if (-not $Python) {
    $venv = Join-Path $repo ".venv-win\Scripts\python.exe"
    $Python = if (Test-Path $venv) { $venv } else { "d:\tmp\alan_venv\Scripts\python.exe" }
}
Set-Location $repo
# keep the reference data current: yesterday's VXN close is the gate, the event calendar the skip list
& $Python -m scripts.bootstrap_market_data --intraday-only --events 2>&1 | Select-Object -Last 3
& $Python -m scripts.bootstrap_market_data 2>&1 | Select-Object -Last 2
# run the session; if the process dies before 16:01 ET (crash, network), start it again: it resumes from paper_state/
$attempt = 0
do {
    $attempt++
    & $Python -m scripts.paper_runner --strategy $Strategy --poll $Poll --notify @extra
    $code = $LASTEXITCODE
    $nowEt = [System.TimeZoneInfo]::ConvertTimeBySystemTimeZoneId((Get-Date), "Eastern Standard Time")
    if ($code -ne 0 -and $nowEt.TimeOfDay -lt [TimeSpan]"16:01" -and $attempt -lt 20) { Start-Sleep -Seconds 30 }
} while ($code -ne 0 -and $nowEt.TimeOfDay -lt [TimeSpan]"16:01" -and $attempt -lt 20)
# after the close: store today's NDX minutes and NDXP prints, then reconcile the paper log against the replay
$today = (Get-Date).ToString("yyyy-MM-dd")
& $Python -m scripts.bootstrap_market_data --intraday-only --intraday NDX --option-minutes NDX --option-minutes-from $today 2>&1 | Select-Object -Last 3
& $Python -m scripts.bootstrap_market_data 2>&1 | Select-Object -Last 2     # daily closes are final now (the 10:30 run stored none for today)
& $Python -m scripts.check_data_day --day $today --notify
Set-Location $strategies
& $Python strategies\$Strategy\scripts\reconcile_paper.py $today --out "strategies\$Strategy\paper_log\reconcile_$today.md"
# archive the day: event log, runner diary, state, heartbeat, reconciliation and the ledger rows into
# strategies\<strategy>\paper_log\archive\<date>\ plus a dated zip in D:\Work\Project Dream\alan-trader-logs
Set-Location $repo
& $Python -m scripts.archive_paper_day --strategy $Strategy --day $today
