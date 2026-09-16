"""Create selected media variants from lossless source frames."""

import json
import math
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

import imageio_ffmpeg
from PIL import Image
from rlottie_python import LottieAnimation

from emojigif.convert import (
    MAX_FILE_BYTES,
    MAX_PIXELS,
    MAX_SECONDS,
    ConversionError,
    gif_frame,
    hidden_process_options,
    read_lottie,
    save_gif,
)
from emojigif.settings import DEFAULT_SETTINGS, ExportSettings

EXPORT_SIZES = (128, 256, 512)
MAX_ARCHIVE_BYTES = 45 * 1024 * 1024


def fit_size(width: int, height: int, size: int) -> tuple[int, int]:
    scale = size / max(width, height)
    return max(1, round(width * scale)), max(1, round(height * scale))


def write_frame(image: Image.Image, folder: Path, index: int, settings: ExportSettings) -> None:
    rgba = image.convert("RGBA")
    rgba = rgba.resize(fit_size(*rgba.size, max(settings.sizes)), Image.Resampling.LANCZOS)
    if settings.background != "transparent":
        background = Image.new("RGBA", rgba.size, settings.background)
        background.alpha_composite(rgba)
        rgba = background
    rgba.save(folder / f"frame-{index:04}.png")


def ffmpeg(arguments: list[str]) -> None:
    try:
        subprocess.run(
            [
                imageio_ffmpeg.get_ffmpeg_exe(),
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-y",
                "-threads",
                "2",
                "-filter_threads",
                "1",
                "-filter_complex_threads",
                "1",
                *arguments,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=60,
            **hidden_process_options(),
        )
    except subprocess.TimeoutExpired as exc:
        raise ConversionError(
            "Video encoding took too long. Reduce the size or frame rate."
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise ConversionError("Could not create a video from this file.") from exc


def render_frames(
    source: Path, folder: Path, settings: ExportSettings = DEFAULT_SETTINGS
) -> list[Path]:
    if source.stat().st_size > MAX_FILE_BYTES:
        raise ConversionError("The file exceeds 10 MB.")
    folder.mkdir()
    suffix, fps = source.suffix.lower(), settings.fps
    only_png = settings.png == "only"
    if suffix == ".tgs":
        data = read_lottie(source)
        duration = (data["op"] - data.get("ip", 0)) / data["fr"]
        with LottieAnimation.from_data(json.dumps(data)) as animation:
            rate = animation.lottie_animation_get_framerate()
            total = animation.lottie_animation_get_totalframe()
            if total <= 0 or rate <= 0 or duration > MAX_SECONDS:
                raise ConversionError("Invalid TGS duration.")
            width, height = fit_size(*animation.lottie_animation_get_size(), max(settings.sizes))
            count = 1 if only_png else min(MAX_SECONDS * fps, max(1, math.ceil(duration * fps)))
            for index in range(count):
                frame = animation.render_pillow_frame(
                    frame_num=min(total - 1, int(index * rate / fps)),
                    width=width,
                    height=height,
                )
                frame = Image.frombytes("RGBa", frame.size, frame.tobytes()).convert("RGBA")
                write_frame(frame, folder, index, settings)
    elif suffix in {".png", ".webp"}:
        with Image.open(source) as image:
            if image.width * image.height > MAX_PIXELS:
                raise ConversionError("The image dimensions are too large.")
            count = 1 if only_png else getattr(image, "n_frames", 1)
            if count > MAX_SECONDS * 60:
                raise ConversionError("The file contains too many frames.")
            elapsed, emitted = 0, 0
            for index in range(count):
                image.seek(index)
                image.load()  # WebP duration is populated only after decoding the frame.
                elapsed += max(20, int(image.info.get("duration", 100)))
                if elapsed > MAX_SECONDS * 1000 and not only_png:
                    raise ConversionError("The animation must be no longer than 10 seconds.")
                target = 1 if count == 1 else math.ceil(elapsed * fps / 1000)
                while emitted < target:
                    write_frame(image, folder, emitted, settings)
                    emitted += 1
    elif suffix == ".webm":
        size = max(settings.sizes)
        scale = (
            f"scale={size}:{size}:force_original_aspect_ratio=decrease:"
            "flags=lanczos+accurate_rnd,setsar=1"
        )
        filters = scale if only_png else f"fps={fps},{scale}"
        ffmpeg(
            [
                "-protocol_whitelist",
                "file,pipe",
                "-c:v",
                "libvpx-vp9",
                "-i",
                str(source),
                "-t",
                str(MAX_SECONDS),
                "-vf",
                filters,
                "-frames:v",
                str(1 if only_png else MAX_SECONDS * fps),
                "-pix_fmt",
                "rgba",
                "-start_number",
                "0",
                str(folder / "frame-%04d.png"),
            ]
        )
        if settings.background != "transparent":
            for index, path in enumerate(sorted(folder.glob("frame-*.png"))):
                with Image.open(path) as image:
                    copy = image.copy()
                write_frame(copy, folder, index, settings)
    else:
        raise ConversionError("Supported file types: TGS, WEBM, WEBP, and PNG.")
    frames = sorted(folder.glob("frame-*.png"))
    if not frames:
        raise ConversionError("The file contains no frames.")
    return frames


def export_size(frames: list[Path], size: int, folder: Path, settings: ExportSettings) -> None:
    folder.mkdir()
    with Image.open(frames[0]) as first:
        dimensions = fit_size(*first.size, size)
        if settings.png != "none":
            first.resize(dimensions, Image.Resampling.LANCZOS).save(folder / "first-frame.png")
    formats, fps = settings.effective_formats, settings.fps
    if "gif" in formats:
        palette_frames = []
        for path in frames:
            with Image.open(path) as frame:
                palette_frames.append(
                    gif_frame(
                        frame.resize(dimensions, Image.Resampling.LANCZOS),
                        size,
                        colors=127 if settings.quality == "small" else 255,
                    )
                )
        save_gif(palette_frames, [1000 // fps] * len(palette_frames), folder / "emoji.gif")
        for frame in palette_frames:
            frame.close()
        del palette_frames

    duration = settings.still_seconds if len(frames) == 1 else len(frames) / fps
    inputs = ["-loop", "1"] if len(frames) == 1 else []
    inputs += ["-framerate", str(fps), "-i", str(frames[0].parent / "frame-%04d.png")]
    width, height = dimensions
    even_w, even_h = width + width % 2, height + height % 2
    scale = f"scale={width}:{height}:flags=lanczos+accurate_rnd,setsar=1"
    pad_color = "black@0" if settings.background == "transparent" else settings.background
    transparent = f"{scale},pad={even_w}:{even_h}:0:0:color={pad_color}"
    if "webm" in formats:
        ffmpeg(
            [
                *inputs,
                "-t",
                str(duration),
                "-vf",
                f"{transparent},format=yuva420p",
                "-c:v",
                "libvpx-vp9",
                "-threads",
                "2",
                "-b:v",
                "0",
                "-crf",
                {"small": "36", "balanced": "24", "high": "0"}[settings.quality],
                "-lossless",
                "1" if settings.quality == "high" else "0",
                "-deadline",
                "good",
                "-cpu-used",
                "4",
                "-auto-alt-ref",
                "0",
                "-an",
                str(folder / "emoji.webm"),
            ]
        )
    if "mp4" in formats:
        background = "black" if settings.background == "black" else "white"
        ffmpeg(
            [
                *inputs,
                "-t",
                str(duration),
                "-filter_complex",
                f"[0:v]{scale}[fg];color=c={background}:s={even_w}x{even_h}:r={fps}[bg];"
                "[bg][fg]overlay=shortest=1:format=auto,format=yuv420p[v]",
                "-map",
                "[v]",
                "-c:v",
                "libx264",
                "-threads",
                "2",
                "-preset",
                "fast",
                "-crf",
                {"small": "28", "balanced": "22", "high": "18"}[settings.quality],
                "-movflags",
                "+faststart",
                "-an",
                str(folder / "emoji.mp4"),
            ]
        )
    if "mov" in formats:
        # MOV is the container; ProRes 4444 preserves the source alpha channel.
        ffmpeg(
            [
                *inputs,
                "-t",
                str(duration),
                "-vf",
                f"{transparent},format=yuva444p10le",
                "-c:v",
                "prores_ks",
                "-threads",
                "2",
                "-profile:v",
                "4",
                "-alpha_bits",
                "16",
                "-vendor",
                "apl0",
                "-qscale:v",
                {"small": "13", "balanced": "9", "high": "5"}[settings.quality],
                "-an",
                str(folder / "emoji.mov"),
            ]
        )
    if any(not 0 < path.stat().st_size <= MAX_ARCHIVE_BYTES for path in folder.iterdir()):
        raise ConversionError(
            "One file exceeds 45 MB. Reduce the sizes, frame rate, or number of formats."
        )


def create_bundle(source: Path, output: Path, settings: ExportSettings = DEFAULT_SETTINGS) -> None:
    with TemporaryDirectory(prefix="media-export-", dir=output.parent) as directory:
        work = Path(directory)
        frames = render_frames(source, work / "frames", settings)
        result = work / "result"
        result.mkdir()
        for size in settings.sizes:
            export_size(frames, size, result / str(size), settings)
        temporary_zip = work / "bundle.zip"
        with ZipFile(temporary_zip, "w", compression=ZIP_DEFLATED) as archive:
            for path in sorted(result.rglob("*")):
                if path.is_file():
                    archive.write(path, arcname=path.relative_to(result).as_posix())
        if temporary_zip.stat().st_size > MAX_ARCHIVE_BYTES:
            raise ConversionError(
                "The archive exceeds 45 MB. "
                "Select fewer sizes or formats, or reduce the frame rate."
            )
        shutil.move(str(temporary_zip), str(output))
