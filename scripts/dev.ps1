$root = Resolve-Path "$PSScriptRoot\.."
Start-Process powershell -ArgumentList "-NoExit","-Command","cd '$root\backend'; .\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000"
Start-Process powershell -ArgumentList "-NoExit","-Command","cd '$root\frontend'; npm run dev"
Write-Host "API http://127.0.0.1:8000/docs   Web http://localhost:3000"
