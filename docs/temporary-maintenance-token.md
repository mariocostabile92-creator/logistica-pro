# Temporary Maintenance Token

Un Administrator autenticato genera il token da **Organizzazione → Diagnostica**.
Il valore viene mostrato solo nella risposta di creazione, dura 15 minuti per
impostazione predefinita (massimo 30) ed è limitato allo scope
`PLANNING_COVERAGE_BACKFILL`.

Usare il valore solo in memoria e non salvarlo nel repository o in un file `.env`:

```powershell
$temporaryMaintenanceToken = Read-Host "Token manutenzione"
curl.exe -H "Authorization: Bearer $temporaryMaintenanceToken" `
  "https://example.invalid/api/plugins/workforce/v1/planning/coverage?date_from=2026-08-10&date_to=2026-08-16"
Remove-Variable temporaryMaintenanceToken
```

Lo stesso header è accettato esclusivamente da Coverage read, backfill preview e
backfill apply. Tutti gli altri endpoint continuano a richiedere la normale
sessione applicativa. Il token può essere revocato immediatamente tramite
`POST /api/admin/maintenance-tokens/{id}/revoke` da un Administrator della stessa
organizzazione.
