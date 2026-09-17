# Registers (or replaces) the Windows Task Scheduler entry that starts the paper runner on trading days.
# The trigger is 10:30 ET converted to this machine's local time; the runner itself waits for the open
# and exits after 16:01 ET, and the start script refreshes data first and reconciles after the close.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\register_paper_task.ps1            # register
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\register_paper_task.ps1 -Remove    # remove
param(
    [string]$TaskName = "AlanTrader paper NDX",
    [string]$Strategy = "ndx_0dte_tasty",
    [switch]$Remove
)
$script = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "start_paper_runner.ps1"
if ($Remove) {
    schtasks /Delete /TN "$TaskName" /F | Out-Null
    "removed task '$TaskName'"
    return
}
$et = [System.TimeZoneInfo]::FindSystemTimeZoneById("Eastern Standard Time")
$todayEt = [System.TimeZoneInfo]::ConvertTimeFromUtc([DateTime]::UtcNow, $et).Date
$startEt = $todayEt.AddHours(10).AddMinutes(30)
$startLocal = [System.TimeZoneInfo]::ConvertTime([DateTime]::SpecifyKind($startEt, [DateTimeKind]::Unspecified), $et, [System.TimeZoneInfo]::Local)
$st = $startLocal.ToString("HH:mm")
$tr = "powershell -NoProfile -ExecutionPolicy Bypass -File `"$script`" -Strategy $Strategy"
schtasks /Create /F /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST $st /TN "$TaskName" /TR "$tr" | Out-Null
"registered '$TaskName': weekdays at $st local (10:30 ET) -> $script"
"note: the local time is fixed at registration; re-run this after a daylight-saving change"
schtasks /Query /TN "$TaskName" /FO LIST | Select-String -Pattern "TaskName|Next Run Time|Status"
