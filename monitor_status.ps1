#!/usr/bin/env pwsh
# Monitor solar mining status

$AUTH = "8E0095E025BA0C4A85B7741A"
$headers = @{ "Authorization" = $AUTH }

Write-Host "`n" ("="*70)
Write-Host "  SOLAR MINING STATUS MONITOR" -ForegroundColor Cyan
Write-Host ("="*70) "`n"

# Check QuickMiner API
try {
    $info = Invoke-RestMethod -Uri "http://localhost:18000/info" -Headers $headers -ErrorAction Stop
    Write-Host "✅ QuickMiner Connected" -ForegroundColor Green
    Write-Host "   Version: $($info.version)"
    Write-Host "   Uptime: $($info.uptime)s"
    Write-Host ""
} catch {
    Write-Host "❌ QuickMiner API not responding" -ForegroundColor Red
    Write-Host ""
    exit 1
}

# Check mining status
try {
    $workers = Invoke-RestMethod -Uri "http://localhost:18000/workers" -Headers $headers
    
    if ($workers.workers.Count -gt 0) {
        Write-Host "⛏️  MINING: ACTIVE" -ForegroundColor Green
        Write-Host ("="*70)
        foreach ($w in $workers.workers) {
            $algo = $w.algorithms[0]
            $hashrate = [math]::Round($algo.speed/1000000, 2)
            Write-Host "   GPU $($w.device_id): $($algo.name) @ ${hashrate} MH/s"
        }
    } else {
        Write-Host "⛏️  MINING: STOPPED" -ForegroundColor Yellow
        Write-Host ("="*70)
        Write-Host "   Waiting for solar power checks..."
    }
} catch {
    Write-Host "❌ Could not get worker status" -ForegroundColor Red
}

Write-Host ""

# Check latest solar data
if (Test-Path "logs\solar_data.csv") {
    $lastLine = Get-Content "logs\solar_data.csv" -Tail 1
    if ($lastLine) {
        $fields = $lastLine -split ","
        if ($fields.Count -gt 10) {
            $timestamp = $fields[0]
            $solar = $fields[2]
            $consumption = $fields[3]
            $available = $fields[4]
            
            Write-Host "📊 LATEST SOLAR DATA" -ForegroundColor Cyan
            Write-Host ("="*70)
            Write-Host "   Time: $timestamp"
            Write-Host "   Solar Power: ${solar}W"
            Write-Host "   Consumption: ${consumption}W"
            Write-Host "   Available: ${available}W"
            Write-Host ""
            
            if ([int]$available -ge 800) {
                Write-Host "   🟢 Sufficient power for 2 GPUs (>= 800W)" -ForegroundColor Green
            } elseif ([int]$available -ge 400) {
                Write-Host "   🟡 Sufficient power for 1 GPU (>= 400W)" -ForegroundColor Yellow
            } else {
                Write-Host "   🔴 Insufficient power for mining (< 400W)" -ForegroundColor Red
            }
        }
    }
}

Write-Host ""
Write-Host ("="*70)
Write-Host "  Refresh: Run this script again to update status"
Write-Host ("="*70) "`n"
