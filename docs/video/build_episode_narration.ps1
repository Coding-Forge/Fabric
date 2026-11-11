param(
    [ValidatePattern("^\d{2}$")]
    [string]$Episode = "01",
    [ValidateSet("Microsoft Zira Desktop", "Microsoft David Desktop")]
    [string]$Voice = "Microsoft Zira Desktop"
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Speech
Add-Type -ReferencedAssemblies System.Speech -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Speech.AudioFormat;
using System.Speech.Synthesis;

public class NarrationWord {
    public double start;
    public int position;
    public int length;
}

public static class OfflineEpisodeNarration {
    public static NarrationWord[] Render(string text, string path, string voice) {
        var words = new List<NarrationWord>();
        using (var synth = new SpeechSynthesizer()) {
            synth.SelectVoice(voice);
            synth.Rate = -1;
            synth.SpeakProgress += (sender, e) => words.Add(new NarrationWord {
                start = e.AudioPosition.TotalSeconds,
                position = e.CharacterPosition,
                length = e.CharacterCount
            });
            // Avoid sample-rate conversion drift in Zira's reported word offsets.
            synth.SetOutputToWaveFile(path, new SpeechAudioFormatInfo(
                16000, AudioBitsPerSample.Sixteen, AudioChannel.Mono));
            synth.Speak(text);
        }
        return words.ToArray();
    }
}
'@

$directory = Join-Path $PSScriptRoot "output/episode-$Episode-pilot"
$inputPath = Join-Path $directory "scenes.json"
$manifest = Get-Content -LiteralPath $inputPath -Raw -Encoding UTF8 | ConvertFrom-Json
$slides = @()
foreach ($slide in $manifest.slides) {
    $audio = "slide-{0:D2}.wav" -f [int]$slide.index
    $words = @([OfflineEpisodeNarration]::Render(
        $slide.text, (Join-Path $directory $audio), $Voice
    ))
    if ($words.Count -eq 0) { throw "No speech timing for slide $($slide.index)." }
    $slides += @{
        index = $slide.index
        audio = $audio
        words = $words
    }
    Write-Output "Narrated slide $($slide.index): $($words.Count) timed words."
}
@{
    inputSha256 = (Get-FileHash -LiteralPath $inputPath -Algorithm SHA256).Hash.ToLowerInvariant()
    voice = $Voice
    rate = -1
    slides = $slides
} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $directory "speech.json") -Encoding UTF8
Write-Output "Offline episode $Episode narration and word timing saved in $directory."
