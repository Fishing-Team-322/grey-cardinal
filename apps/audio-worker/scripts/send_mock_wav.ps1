param(
    [string]$Server = "http://localhost:8020",
    [string]$Token = "dev-internal-token",
    [string]$MeetingId = "demo-meeting",
    [int]$ChunkSeq = 1
)

$sampleRate = 16000
$channels = 1
$bitsPerSample = 16
$durationSeconds = 1
$byteRate = $sampleRate * $channels * ($bitsPerSample / 8)
$blockAlign = $channels * ($bitsPerSample / 8)
$dataSize = [int]($byteRate * $durationSeconds)

$memory = New-Object System.IO.MemoryStream
$writer = New-Object System.IO.BinaryWriter($memory)

$writer.Write([System.Text.Encoding]::ASCII.GetBytes("RIFF"))
$writer.Write([UInt32](36 + $dataSize))
$writer.Write([System.Text.Encoding]::ASCII.GetBytes("WAVE"))
$writer.Write([System.Text.Encoding]::ASCII.GetBytes("fmt "))
$writer.Write([UInt32]16)
$writer.Write([UInt16]1)
$writer.Write([UInt16]$channels)
$writer.Write([UInt32]$sampleRate)
$writer.Write([UInt32]$byteRate)
$writer.Write([UInt16]$blockAlign)
$writer.Write([UInt16]$bitsPerSample)
$writer.Write([System.Text.Encoding]::ASCII.GetBytes("data"))
$writer.Write([UInt32]$dataSize)
$writer.Write((New-Object byte[] $dataSize))
$writer.Flush()

$headers = @{
    "X-Internal-Token" = $Token
    "X-Meeting-Id" = $MeetingId
    "X-Chunk-Seq" = "$ChunkSeq"
    "X-Audio-Format" = "wav"
}

Invoke-RestMethod -Method Post -Uri "$Server/audio/chunk" -Headers $headers -ContentType "audio/wav" -Body $memory.ToArray()

