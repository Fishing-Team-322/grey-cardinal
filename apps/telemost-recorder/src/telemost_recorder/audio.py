from __future__ import annotations

import asyncio
from pathlib import Path


class AudioSegmenter:
    def __init__(self, directory: Path, segment_seconds: int) -> None:
        self.directory = directory
        self.segment_seconds = segment_seconds
        self.process: asyncio.subprocess.Process | None = None
        self.uploaded: set[Path] = set()

    async def start(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        self.process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-f",
            "pulse",
            "-i",
            "telemost_sink.monitor",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            "-f",
            "segment",
            "-segment_time",
            str(self.segment_seconds),
            "-reset_timestamps",
            "1",
            str(self.directory / "chunk-%06d.wav"),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )

    def ready_chunks(self, *, include_latest: bool = False) -> list[Path]:
        chunks = sorted(self.directory.glob("chunk-*.wav"))
        if not include_latest and self.process and self.process.returncode is None:
            chunks = chunks[:-1]
        return [path for path in chunks if path not in self.uploaded and path.stat().st_size > 44]

    def mark_uploaded(self, path: Path) -> None:
        self.uploaded.add(path)
        path.unlink(missing_ok=True)

    async def stop(self) -> None:
        if self.process is None or self.process.returncode is not None:
            return
        self.process.terminate()
        try:
            await asyncio.wait_for(self.process.wait(), timeout=10)
        except TimeoutError:
            self.process.kill()
            await self.process.wait()

    async def error_text(self) -> str:
        if not self.process or not self.process.stderr:
            return ""
        return (await self.process.stderr.read()).decode(errors="replace")[-1000:]
