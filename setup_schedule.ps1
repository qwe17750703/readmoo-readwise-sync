# 註冊 Windows 排程：每天執行 Readmoo → Readwise 同步
#
# 使用方式（在 PowerShell 中）：
#   .\setup_schedule.ps1                 # 預設每天 09:00 執行
#   .\setup_schedule.ps1 -Time "21:30"   # 指定時間
#   .\setup_schedule.ps1 -RemoveOnly     # 只移除既有排程
#
# 注意：不需要系統管理員權限，會以「目前使用者」身份執行

param(
    [string]$Time = "09:00",
    [switch]$RemoveOnly
)

$TaskName = "ReadmooToReadwiseSync"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BatPath = Join-Path $ScriptDir "run_sync.bat"

# 先移除舊的（如果存在）
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "移除既有排程：$TaskName"
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

if ($RemoveOnly) {
    Write-Host "已移除排程，結束。"
    exit 0
}

if (-not (Test-Path $BatPath)) {
    Write-Host "找不到 $BatPath，請先確認檔案存在。" -ForegroundColor Red
    exit 1
}

# 建立 action / trigger / settings / principal
$action = New-ScheduledTaskAction -Execute $BatPath -WorkingDirectory $ScriptDir
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1)
$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "每天自動將 Readmoo 畫線同步到 Readwise" | Out-Null

Write-Host ""
Write-Host "排程建立成功！" -ForegroundColor Green
Write-Host "  名稱：$TaskName"
Write-Host "  時間：每天 $Time"
Write-Host "  指令：$BatPath"
Write-Host ""
Write-Host "你可以做的事："
Write-Host "  - 在「工作排程器」中查看任務（搜尋 $TaskName）"
Write-Host "  - 立即測試執行：     Start-ScheduledTask -TaskName $TaskName"
Write-Host "  - 查看執行紀錄：     Get-Content sync.log -Tail 30"
Write-Host "  - 移除排程：         .\setup_schedule.ps1 -RemoveOnly"
