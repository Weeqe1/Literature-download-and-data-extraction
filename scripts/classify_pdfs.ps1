param(
    [string]$PdfDir = "D:\Desktop\DATA-Download_Extraction\outputs\literature\PDF",
    [string]$BackupDir = "D:\Desktop\DATA-Download_Extraction\outputs\literature\invalid_backup"
)

# Enable long paths
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Move-Item "$PdfDir\*" $BackupDir -ErrorAction SilentlyContinue
Write-Host "Moved all files from PDF to backup: $( (Get-ChildItem $BackupDir).Count )"
