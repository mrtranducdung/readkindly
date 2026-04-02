from __future__ import annotations
from pathlib import Path
from moviepy import ImageClip, AudioFileClip, concatenate_videoclips

WIDTH = 1080
HEIGHT = 1920

def render_video(scene_paths: list[Path], story_pack, narration_path: Path, out_path: Path) -> None:
    clips = []
    for scene, scene_path in zip(story_pack.scenes, scene_paths):
        clip = ImageClip(str(scene_path), duration=scene.duration_seconds).resized((WIDTH, HEIGHT))
        clips.append(clip)
    video = concatenate_videoclips(clips, method="compose")
    audio = AudioFileClip(str(narration_path))
    final = video.with_audio(audio)
    final.write_videofile(
        str(out_path),
        fps=24,
        codec="libx264",
        audio_codec="aac",
        threads=4,
        preset="medium",
        logger=None,
    )
