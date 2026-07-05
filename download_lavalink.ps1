# download_lavalink.ps1
# Helper script to download Lavalink.jar for local development

$url = "https://github.com/lavalink-devs/Lavalink/releases/download/4.2.2/Lavalink.jar"
$output = "Lavalink.jar"

Write-Host "Downloading Lavalink v4.2.2..."
Write-Host "From: $url"
Write-Host "To:   $PWD\$output"

try {
    Invoke-WebRequest -Uri $url -OutFile $output -UserAgent "Mozilla/5.0"
    Write-Host "Download successful! Run with 'java -jar Lavalink.jar' after verifying Java 17+ is installed." -ForegroundColor Green
} catch {
    Write-Error "Failed to download Lavalink.jar: $_"
}
