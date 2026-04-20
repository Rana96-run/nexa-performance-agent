Import-Module Microsoft.Graph.Applications

Write-Host ""
Write-Host "=== Microsoft Advertising Service Principal Creator ===" -ForegroundColor Cyan
Write-Host "Tenant: 8b6fc4da-1c24-432f-b089-2355d22f028d"
Write-Host "App ID: d42ffc93-c136-491d-b4fd-6f18168c68fd"
Write-Host ""
Write-Host "A device code will print below. Open the URL," -ForegroundColor Yellow
Write-Host "paste the code, sign in as a Global Admin of the qoyod tenant." -ForegroundColor Yellow
Write-Host ""

try {
    Connect-MgGraph -TenantId 8b6fc4da-1c24-432f-b089-2355d22f028d -Scopes 'Application.ReadWrite.All' -UseDeviceCode -NoWelcome

    Write-Host ""
    Write-Host "[OK] Signed in. Creating service principal..." -ForegroundColor Green

    $sp = New-MgServicePrincipal -AppId d42ffc93-c136-491d-b4fd-6f18168c68fd
    Write-Host ""
    Write-Host "=== SUCCESS ===" -ForegroundColor Green
    Write-Host ("DisplayName: " + $sp.DisplayName)
    Write-Host ("AppId:       " + $sp.AppId)
    Write-Host ("ObjectId:    " + $sp.Id)
}
catch {
    if ($_.Exception.Message -match 'already exists|duplicate|conflicting') {
        Write-Host ""
        Write-Host "[OK] Service principal already exists. You are good." -ForegroundColor Green
    } else {
        Write-Host ""
        Write-Host ("[ERROR] " + $_.Exception.Message) -ForegroundColor Red
    }
}
finally {
    try { Disconnect-MgGraph | Out-Null } catch {}
}

Write-Host ""
Write-Host "Press Enter to close..."
Read-Host
