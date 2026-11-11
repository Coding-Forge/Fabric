param(
    [ValidateSet("Microsoft Zira Desktop", "Microsoft David Desktop")]
    [string]$Voice = "Microsoft Zira Desktop"
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Speech

$outputDirectory = Join-Path $PSScriptRoot "output"
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
$outputPath = Join-Path $outputDirectory "narration-preview.wav"
$text = Get-Content -LiteralPath (Join-Path $PSScriptRoot "narration-preview.txt") -Raw
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer

try {
    $synth.SelectVoice($Voice)
    $synth.Rate = -1
    $format = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(
        24000,
        [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,
        [System.Speech.AudioFormat.AudioChannel]::Mono
    )
    $synth.SetOutputToWaveFile($outputPath, $format)
    $synth.Speak($text)
}
finally {
    $synth.Dispose()
}

Write-Output "Offline narration preview: $outputPath"
