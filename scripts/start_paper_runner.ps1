# Starts the automated paper runner for one strategy. Schedule it on trading days at 10:30 ET, e.g.:
#   schtasks /Create /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 10:30 /TN "AlanTrader paper NDX" ^
#     /TR "powershell -NoProfile -ExecutionPolicy Bypass -File \"D:\Work\Project Dream\alan_trader\scripts\start_paper_runner.ps1\""
# (adjust /ST to your machine's local time for 10:30 ET). The runner waits for 09:30 ET if started early,
# resumes a session after a crash or restart (paper_state/), and exits after 16:01 ET.
param(
    [string]$Strategy = "ndx_0dte_tasty",
    [string]$Python = "d:\tmp\alan_venv\Scripts\python.exe",
    [int]$Poll = 15
)
$env:PYTHONIOENCODING = "utf-8"
Set-Location "D:\Work\Project Dream\alan_trader"
# keep the reference data current: yesterday's VXN close is the gate, the event calendar the skip list
& $Python -m scripts.bootstrap_market_data --intraday-only --events 2>&1 | Select-Object -Last 3
& $Python -m scripts.bootstrap_market_data 2>&1 | Select-Object -Last 2
& $Python -m scripts.paper_runner --strategy $Strategy --poll $Poll
