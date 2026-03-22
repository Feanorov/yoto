from __future__ import annotations

from pathlib import Path
import subprocess

from ..domain.entities import VideoRenderRequest
from .structured_logger import StructuredLogger


class FFmpegRenderError(RuntimeError):
    pass


class FFmpegRenderer:
    def __init__(self, ffmpeg_bin: str = 'ffmpeg', logger: StructuredLogger | None = None) -> None:
        self.ffmpeg_bin = ffmpeg_bin
        self.logger = logger or StructuredLogger()

    def render(self, request: VideoRenderRequest) -> None:
        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        command = [self.ffmpeg_bin, '-y']
        for scene in request.scenes:
            command.extend(['-loop', '1', '-t', f'{scene.duration_seconds:g}', '-i', str(scene.image_path)])

        input_refs = ''.join(f'[{index}:v]' for index in range(len(request.scenes)))
        filter_complex = f'{input_refs}concat=n={len(request.scenes)}:v=1:a=0[v]'
        command.extend(
            [
                '-filter_complex',
                filter_complex,
                '-map',
                '[v]',
                '-r',
                '30',
                '-c:v',
                'libx264',
                '-preset',
                'veryfast',
                '-crf',
                '23',
                '-pix_fmt',
                'yuv420p',
                str(request.output_path),
            ]
        )

        self.logger.info(
            'ffmpeg started',
            output_path=request.output_path,
            scene_count=len(request.scenes),
            command=command,
        )
        try:
            completed = subprocess.run(command, capture_output=True, text=True, check=False)
        except FileNotFoundError as exc:
            raise FFmpegRenderError(
                f'ffmpeg executable not found: {self.ffmpeg_bin}. Install FFmpeg and make it available on PATH, '
                'or pass --ffmpeg-bin with the full executable path.'
            ) from exc

        if completed.returncode != 0:
            raise FFmpegRenderError(completed.stderr.strip() or completed.stdout.strip() or 'ffmpeg render failed')

        self.logger.info('video exported', output_path=request.output_path)
