from __future__ import annotations

"""
Full automation scaffold for a short-form moral-story pipeline:
- story generation
- scene planning
- image prompt generation
- TTS narration generation
- subtitle generation
- ffmpeg video assembly
- optional TikTok upload using the official Content Posting API

Notes
-----
This file is production-oriented, but provider-specific pieces still need your API
keys and model choices. The TikTok flow here targets the official v2 Content
Posting API flow.
"""

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Dict, Any, Optional
import json
import os
import random
import subprocess
import requests


@dataclass
class Character:
    name: str
    description: str


@dataclass
class StoryIdea:
    topic: str
    moral: str
    main_character: str = "Lumi, a cute and kind elf boy"
    audience_age: str = "4-9"
    visual_style: str = "cute anime, warm, funny, wholesome"
    language: str = "en"
    duration_seconds: int = 55
    scene_count: int = 10


@dataclass
class Scene:
    index: int
    title: str
    narration: str
    on_screen_text: str
    image_prompt: str
    duration_seconds: float
    image_path: Optional[str] = None


@dataclass
class StoryPackage:
    title: str
    hook: str
    moral: str
    hook_image_prompt: str
    scenes: List[Scene]
    outro: str
    character_consistency_prompt: str = ""
    hashtags: List[str] = field(default_factory=list)
    characters: List[Character] = field(default_factory=list)
    hook_image_path: Optional[str] = None


@dataclass
class NarrationPackage:
    full_script: str
    audio_path: str
    subtitles_path: str
    scene_durations: List[float] = field(default_factory=list)
    hook_dur: float = 0.0
    outro_dur: float = 0.0
    silence_between: float = 0.0


@dataclass
class VideoPackage:
    video_path: str
    thumbnail_path: Optional[str]
    duration_seconds: float


class Agent:
    def __init__(self, name: str):
        self.name = name

    def run(self, *args, **kwargs):
        raise NotImplementedError


class StoryAgent(Agent):
    CONFIG_PATH = Path("story_config.json")

    def __init__(self):
        super().__init__("story_agent")

    def run(self, idea: StoryIdea) -> StoryPackage:
        if self.CONFIG_PATH.exists():
            print(f"Loading story from {self.CONFIG_PATH}")
            return self._load_from_json(self.CONFIG_PATH)
        print("No story_config.json found — using default story.")
        return self._default_story(idea)

    def _load_from_json(self, path: Path) -> StoryPackage:
        data = json.loads(path.read_text(encoding="utf-8"))
        scenes = [
            Scene(
                index=s["index"],
                title=s["title"],
                narration=s["narration"],
                on_screen_text=s["on_screen_text"],
                image_prompt=s["image_prompt"],
                duration_seconds=float(s["duration_seconds"]),
            )
            for s in data["scenes"]
        ]
        characters = [
            Character(name=c["name"], description=c["description"])
            for c in data.get("characters", [])
        ]
        return StoryPackage(
            title=data.get("title", scenes[0].title),
            hook=data["hook"],
            moral=data["moral"],
            hook_image_prompt=data.get("hook_image_prompt", data["scenes"][0]["image_prompt"]),
            scenes=scenes,
            outro=data["outro"],
            character_consistency_prompt=data.get("character_consistency_prompt", ""),
            hashtags=data.get("hashtags", []),
            characters=characters,
        )

    def _default_story(self, idea: StoryIdea) -> StoryPackage:
        scenes = [
            Scene(1, "Morning", "Lumi woke up in the sunny forest, ready for adventure.", "A happy new day!", "Cute anime elf boy waking in a magical sunny forest, warm light, same brown hair, elf ears, warm brown eyes, vertical 9:16", 4.0),
            Scene(2, "Bird Helps", "A tiny bird helped Lumi find sweet berries for breakfast.", "A friend helped him.", "Cute elf boy with yellow bird finding berries in the forest, wholesome, same character, vertical 9:16", 5.0),
            Scene(3, "Forgot", "Lumi smiled and ran off so fast that he forgot to say thank you.", "He forgot to say thanks...", "Elf boy running away happily while bird looks confused, emotional cute anime style, vertical 9:16", 5.0),
            Scene(4, "Rabbit Helps", "Later, a rabbit helped him cross the river safely.", "Another friend helped him.", "Cute white rabbit helping elf boy cross a stream on stones, forest, adorable, vertical 9:16", 5.0),
            Scene(5, "Forgot Again", "But once again, Lumi forgot to say thank you.", "He forgot again.", "Elf boy walking away quickly, rabbit slightly sad, anime emotional scene, vertical 9:16", 4.5),
            Scene(6, "Lonely", "Soon, Lumi noticed that no one came to help him anymore.", "Why is everyone gone?", "Elf boy alone in the forest looking confused and sad, soft light, vertical 9:16", 5.0),
            Scene(7, "Realization", "Then Lumi stopped and thought, Oh no, I forgot to thank my friends.", "Oh no!", "Elf boy realizing his mistake, glowing realization moment, forest background, vertical 9:16", 5.0),
            Scene(8, "Apology", "He ran back and said, Thank you for helping me. I am sorry I forgot.", "Thank you. I am sorry.", "Elf boy politely bowing to bird and rabbit, warm and wholesome, vertical 9:16", 6.0),
            Scene(9, "Joy Returns", "The bird chirped, the rabbit smiled, and the forest felt bright again.", "Kindness came back.", "Elf boy celebrating with bird and rabbit in glowing magical forest, sparkles, joyful, vertical 9:16", 5.5),
            Scene(10, "Moral", "Lumi learned that saying thank you makes kindness grow everywhere.", "Say thank you.", "Elf boy smiling with friends in peaceful glowing forest, emotional moral ending, vertical 9:16", 6.0),
        ]
        return StoryPackage(
            title="Lumi and the Magic of Thank You",
            hook="What happens when you forget to say thank you?",
            moral=idea.moral,
            hook_image_prompt="Cute anime elf boy Lumi with his bird and rabbit friends together in a glowing magical forest, warm light, thankful mood, vertical 9:16",
            scenes=scenes,
            outro="Always say thank you. Kindness grows when gratitude grows.",
            character_consistency_prompt="Keep Lumi, the little yellow bird, and the white rabbit visually consistent in every image.",
            hashtags=["#moraltales", "#gratitude", "#kidsstory", "#thankyou", "#storytime", "#animeart"],
        )


class PromptConsistencyAgent(Agent):
    def __init__(self):
        super().__init__("prompt_consistency_agent")

    def run(self, story: StoryPackage) -> StoryPackage:
        if not story.character_consistency_prompt:
            return story
        for scene in story.scenes:
            if story.character_consistency_prompt not in scene.image_prompt:
                scene.image_prompt = f"{scene.image_prompt}, {story.character_consistency_prompt}"
        if story.character_consistency_prompt not in story.hook_image_prompt:
            story.hook_image_prompt = f"{story.hook_image_prompt}, {story.character_consistency_prompt}"
        return story


class ImageAgent(Agent):
    def __init__(self, out_dir: Path, reference_image_path: Optional[str] = None):
        super().__init__("image_agent")
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.reference_image_path = reference_image_path
        self.pipe = None

    def _clear_pipeline(self):
        if self.pipe is None:
            return
        self.pipe = None
        try:
            import gc
            import torch

            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    def _load_pipeline(self, use_ip_adapter: bool = False):
        import torch
        from diffusers import FluxPipeline
        from transformers import CLIPVisionModelWithProjection

        print("Loading FLUX.1-schnell" + (" + IP-Adapter" if use_ip_adapter else "") + " (this takes a minute)...")

        if use_ip_adapter:
            image_encoder = CLIPVisionModelWithProjection.from_pretrained(
                "openai/clip-vit-large-patch14",
                torch_dtype=torch.bfloat16,
            )
            self.pipe = FluxPipeline.from_pretrained(
                "black-forest-labs/FLUX.1-schnell",
                image_encoder=image_encoder,
                torch_dtype=torch.bfloat16,
            )
            self.pipe.load_ip_adapter(
                "XLabs-AI/flux-ip-adapter",
                weight_name="ip_adapter.safetensors",
                image_encoder_folder=None,
            )
        else:
            self.pipe = FluxPipeline.from_pretrained(
                "black-forest-labs/FLUX.1-schnell",
                torch_dtype=torch.bfloat16,
            )

        # Sequential offload lowers peak VRAM use, but it depends on accelerate.
        try:
            self.pipe.enable_sequential_cpu_offload()
        except RuntimeError as exc:
            if "requires accelerator" not in str(exc):
                raise
            print("accelerate not installed; continuing without sequential CPU offload.")
        print("Model loaded.")

    def _render_image(self, prompt: str, out_path: Path, ref_image=None, ip_scale: float = 0.6):
        kwargs = dict(
            prompt=prompt,
            height=1024,
            width=576,
            num_inference_steps=4,
            guidance_scale=0.0,
        )
        if ref_image is not None:
            self.pipe.set_ip_adapter_scale(ip_scale)
            kwargs["ip_adapter_image"] = ref_image
        result = self.pipe(**kwargs)
        result.images[0].save(str(out_path))

    def _composite_refs(self, ref_paths: list) -> "Image":
        """Tile multiple character reference images side-by-side into one PIL image."""
        from PIL import Image
        images = [Image.open(p).convert("RGB") for p in ref_paths]
        w = max(img.width for img in images)
        h = max(img.height for img in images)
        images = [img.resize((w, h)) for img in images]
        combined = Image.new("RGB", (w * len(images), h))
        for i, img in enumerate(images):
            combined.paste(img, (i * w, 0))
        return combined

    def _generate_character_refs(self, characters: list) -> dict:
        """Generate one solo portrait per character (text-only, no IP-Adapter).
        Returns dict mapping lowercased character name -> Path."""
        refs: dict = {}
        if not characters:
            return refs
        self._load_pipeline(use_ip_adapter=False)
        for char in characters:
            name = char.name.strip()
            safe_name = name.lower().replace(" ", "_")
            out_path = self.out_dir / f"ref_{safe_name}.png"
            prompt = (
                f"{name}, {char.description}, solo portrait, full body, "
                "bright cheerful picture-book illustration style, white background, "
                "child-friendly, soft pastel colors"
            )
            print(f"  Generating character reference: {name}...")
            self._render_image(prompt, out_path)
            refs[name.lower()] = out_path
            print(f"    Saved: {out_path}")
        self._clear_pipeline()
        return refs

    def _pick_ref_for_scene(self, prompt: str, char_refs: dict):
        """Return a PIL image: the ref(s) for characters mentioned in the prompt.
        Falls back to all refs composited if no match or only one ref total."""
        from PIL import Image
        if not char_refs:
            return None
        prompt_lower = prompt.lower()
        matched = [path for name, path in char_refs.items() if name in prompt_lower]
        if not matched:
            matched = list(char_refs.values())
        if len(matched) == 1:
            return Image.open(matched[0]).convert("RGB")
        return self._composite_refs(matched)

    def _load_char_refs_from_disk(self) -> dict:
        """Re-load character ref images already on disk (for regenerate_scene)."""
        refs: dict = {}
        for path in sorted(self.out_dir.glob("ref_*.png")):
            name = path.stem[4:].replace("_", " ")  # strip "ref_" prefix
            refs[name] = path
        return refs

    def regenerate_scene(self, scene: Scene, hook_image_path: Path, extra_prompt: str = "", ip_scale: float = 0.6) -> str:
        from PIL import Image

        prompt = scene.image_prompt
        if extra_prompt and extra_prompt not in prompt:
            prompt = f"{prompt}, {extra_prompt}"

        # Prefer per-character refs over hook.png if they exist
        char_refs = self._load_char_refs_from_disk()
        if char_refs:
            ref_image = self._pick_ref_for_scene(prompt, char_refs)
            print(f"  Using character ref(s): {[str(p) for p in char_refs.values()]}")
        elif Path(hook_image_path).exists():
            ref_image = Image.open(hook_image_path).convert("RGB")
            print(f"  Using hook image as reference: {hook_image_path}")
        else:
            raise RuntimeError(f"No character refs and no hook image found at: {hook_image_path}")

        out_path = self.out_dir / f"scene_{scene.index:02d}.png"
        self._load_pipeline(use_ip_adapter=True)
        self._render_image(prompt, out_path, ref_image=ref_image, ip_scale=ip_scale)
        self._clear_pipeline()
        scene.image_path = str(out_path)
        print(f"  Saved: {out_path}")
        return str(out_path)

    def run(self, story: StoryPackage) -> StoryPackage:
        # Step 1: Generate individual character reference images (text-only)
        print("Generating character reference images...")
        char_refs = self._generate_character_refs(story.characters)

        # Step 2: Generate hook image using composited character refs as IP-Adapter reference
        hook_path = self.out_dir / "hook.png"
        print("Generating hook image...")
        if char_refs:
            hook_ref = self._composite_refs(list(char_refs.values()))
            self._load_pipeline(use_ip_adapter=True)
            self._render_image(story.hook_image_prompt, hook_path, ref_image=hook_ref)
        else:
            self._load_pipeline(use_ip_adapter=False)
            self._render_image(story.hook_image_prompt, hook_path)
        story.hook_image_path = str(hook_path)
        print(f"  Saved: {hook_path}")
        self._clear_pipeline()

        # Step 3: Generate each scene using per-scene character refs
        self._load_pipeline(use_ip_adapter=True)
        for scene in story.scenes:
            out_path = self.out_dir / f"scene_{scene.index:02d}.png"
            print(f"Generating scene {scene.index}/{len(story.scenes)}: {scene.title}...")
            ref_image = self._pick_ref_for_scene(scene.image_prompt, char_refs)
            self._render_image(scene.image_prompt, out_path, ref_image=ref_image)
            scene.image_path = str(out_path)
            print(f"  Saved: {out_path}")

        self._clear_pipeline()
        return story


class NarrationAgent(Agent):
    def __init__(self, out_dir: Path, api_key: str, voice_id: str):
        super().__init__("narration_agent")
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.api_key = api_key
        self.voice_id = voice_id

    def _tts(self, text: str, out_path: Path) -> float:
        """Call ElevenLabs for one text chunk, save mp3, return duration in seconds."""
        response = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}",
            headers={"xi-api-key": self.api_key, "Content-Type": "application/json"},
            json={
                "text": text,
                "model_id": "eleven_monolingual_v1",
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
            },
        )
        response.raise_for_status()
        out_path.write_bytes(response.content)
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(out_path)],
            capture_output=True, text=True,
        )
        return float(result.stdout.strip())

    SILENCE_BETWEEN = 0.4  # seconds of pause between scenes

    def run(self, story: StoryPackage) -> NarrationPackage:
        clips_dir = self.out_dir / "clips"
        clips_dir.mkdir(exist_ok=True)
        audio_path = self.out_dir / "narration.mp3"
        subtitles_path = self.out_dir / "captions.srt"

        # Generate silence clip for between-scene pauses
        silence_path = clips_dir / "silence.mp3"
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
            "-t", str(self.SILENCE_BETWEEN), "-c:a", "libmp3lame", "-b:a", "128k",
            str(silence_path),
        ], check=True, capture_output=True)
        silence_dur = float(subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(silence_path)],
            capture_output=True, text=True,
        ).stdout.strip())

        # TTS: hook, all scenes, outro
        print("  TTS: hook...")
        hook_path = clips_dir / "hook.mp3"
        hook_dur = self._tts(story.hook, hook_path)

        scene_durs: List[float] = []
        scene_paths: List[Path] = []
        for scene in story.scenes:
            clip = clips_dir / f"scene_{scene.index:02d}.mp3"
            print(f"  TTS: scene_{scene.index:02d}...")
            scene_durs.append(self._tts(scene.narration, clip))
            scene_paths.append(clip)

        print("  TTS: outro...")
        outro_path = clips_dir / "outro.mp3"
        outro_dur = self._tts(story.outro, outro_path)

        # Audio order: hook → s1 → silence → s2 → silence → ... → s10 → outro
        ordered = [str(hook_path.resolve()), str(scene_paths[0].resolve())]
        for sp in scene_paths[1:]:
            ordered += [str(silence_path.resolve()), str(sp.resolve())]
        ordered.append(str(outro_path.resolve()))

        concat_list = clips_dir / "clips.txt"
        concat_list.write_text("\n".join(f"file '{p}'" for p in ordered), encoding="utf-8")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
             "-i", str(concat_list), "-c", "copy", str(audio_path)],
            check=True, capture_output=True,
        )
        print(f"  Saved: {audio_path}")

        # Save per-scene audio for the webapp player (12-slide model)
        #   hook.mp3  = intro slide audio
        #   outro.mp3 = outro slide audio
        #   scene_01.mp3 … scene_N.mp3 = each scene's own narration
        per_scene_dir = self.out_dir / "scenes"
        per_scene_dir.mkdir(exist_ok=True)

        def _ffmpeg_concat(parts: list, out: Path) -> None:
            txt = per_scene_dir / "_tmp_concat.txt"
            txt.write_text("\n".join(f"file '{Path(p).resolve()}'" for p in parts), encoding="utf-8")
            subprocess.run(
                ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(txt), "-c", "copy", str(out)],
                check=True, capture_output=True,
            )

        # Intro and outro get dedicated audio files
        _ffmpeg_concat([hook_path],  per_scene_dir / "hook.mp3")
        _ffmpeg_concat([outro_path], per_scene_dir / "outro.mp3")
        # Every story scene gets its own narration clip
        for i, sp in enumerate(scene_paths, start=1):
            _ffmpeg_concat([sp], per_scene_dir / f"scene_{i:02d}.mp3")

        print(f"  Saved: {per_scene_dir}/ (hook + outro + {len(scene_paths)} scene clips)")

        subtitles_path.write_text(
            self._build_srt(story, hook_dur, scene_durs, outro_dur, silence_dur),
            encoding="utf-8",
        )
        return NarrationPackage(
            full_script=" ".join([story.hook] + [s.narration for s in story.scenes] + [story.outro]),
            audio_path=str(audio_path),
            subtitles_path=str(subtitles_path),
            scene_durations=scene_durs,
            hook_dur=hook_dur,
            outro_dur=outro_dur,
            silence_between=silence_dur,
        )

    def _build_srt(self, story: StoryPackage, hook_dur: float, scene_durs: List[float],
                   outro_dur: float, silence_dur: float) -> str:
        entries = []
        idx = 1
        t = 0.0

        def add(text: str, dur: float) -> None:
            nonlocal idx, t
            if text:
                entries.append(f"{idx}\n{self._fmt(t)} --> {self._fmt(t + dur)}\n{text}\n")
                idx += 1
            t += dur

        add(story.hook, hook_dur)
        add(story.scenes[0].narration, scene_durs[0])
        for i, scene in enumerate(story.scenes[1:], 1):
            add("", silence_dur)   # silence — no subtitle shown
            add(scene.narration, scene_durs[i])
        add(story.outro, outro_dur)
        return "\n".join(entries)

    def _fmt(self, sec: float) -> str:
        ms = int((sec - int(sec)) * 1000)
        total = int(sec)
        s = total % 60
        m = (total // 60) % 60
        h = total // 3600
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


class VideoAgent(Agent):
    def __init__(self, out_dir: Path):
        super().__init__("video_agent")
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def _audio_duration(self, audio_path: str) -> float:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
            capture_output=True, text=True,
        )
        return float(result.stdout.strip())

    FADE_DUR = 0.15  # seconds for fade-to-black per clip

    def _make_scene_clip(self, image_path: str, dur: float, out_path: Path) -> None:
        """Render one scene as a video clip with fade-in and fade-out."""
        fd = self.FADE_DUR
        subprocess.run([
            "ffmpeg", "-y",
            "-loop", "1", "-t", str(dur),
            "-i", str(Path(image_path).resolve()),
            "-vf", (
                f"scale=576:1024:force_original_aspect_ratio=decrease,"
                f"pad=576:1024:(ow-iw)/2:(oh-ih)/2:black,"
                f"fps=25,"
                f"fade=in:st=0:d={fd},"
                f"fade=out:st={dur - fd:.3f}:d={fd}"
            ),
            "-c:v", "libx264", "-crf", "23", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-an", str(out_path),
        ], check=True, capture_output=True)

    def run(self, story: StoryPackage, narration: NarrationPackage) -> VideoPackage:
        video_path = self.out_dir / "story_video.mp4"
        thumb_path = self.out_dir / "thumb.jpg"
        clips_dir = self.out_dir / "clips"
        clips_dir.mkdir(exist_ok=True)
        srt_abs = str(Path(narration.subtitles_path).resolve())

        audio_dur = self._audio_duration(narration.audio_path)

        clip_specs = []
        if narration.scene_durations and narration.hook_dur and narration.outro_dur:
            silence = narration.silence_between
            if story.hook_image_path:
                clip_specs.append(("hook", story.hook_image_path, narration.hook_dur, "hook"))
            for idx, (scene, dur) in enumerate(zip(story.scenes, narration.scene_durations)):
                extra = silence if idx < len(story.scenes) - 1 else narration.outro_dur + 0.3
                clip_specs.append((scene.index, scene.image_path, dur + extra, f"scene_{scene.index:02d}"))
        else:
            total = sum(sc.duration_seconds for sc in story.scenes)
            scale = audio_dur / total
            if story.hook_image_path:
                clip_specs.append(("hook", story.hook_image_path, min(3.0, audio_dur * 0.15), "hook"))
            for scene in story.scenes:
                clip_specs.append((scene.index, scene.image_path, scene.duration_seconds * scale, f"scene_{scene.index:02d}"))

        clip_files = []
        for label, image_path, dur, filename in clip_specs:
            clip_path = clips_dir / f"{filename}.mp4"
            print(f"  Rendering clip {label}/{len(clip_specs)}...")
            self._make_scene_clip(image_path, dur, clip_path)
            clip_files.append(str(clip_path.resolve()))

        # Concat all scene clips into one video stream
        concat_path = self.out_dir / "concat.txt"
        concat_path.write_text("\n".join(f"file '{f}'" for f in clip_files), encoding="utf-8")

        print("Assembling final video with audio + subtitles...")
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_path),
            "-i", narration.audio_path,
            "-vf", (
                f"subtitles={srt_abs}:force_style="
                f"'FontName=Arial,FontSize=13,PrimaryColour=&H00FFFFFF,"
                f"OutlineColour=&H00000000,Outline=2,Alignment=2,MarginV=40'"
            ),
            "-c:v", "libx264", "-crf", "23", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k",
            "-t", str(audio_dur + 0.3),
            str(video_path),
        ], check=True)

        # Extract thumbnail at 2s (avoids black fade-in at frame 0)
        subprocess.run([
            "ffmpeg", "-y", "-ss", "2", "-i", str(video_path),
            "-vframes", "1", "-q:v", "2", str(thumb_path),
        ], check=True)

        # Embed thumbnail as cover art inside the MP4
        cover_path = self.out_dir / "story_video_cover.mp4"
        subprocess.run([
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(thumb_path),
            "-map", "0", "-map", "1",
            "-c", "copy",
            "-disposition:v:1", "attached_pic",
            str(cover_path),
        ], check=True, capture_output=True)
        cover_path.replace(video_path)

        # Save accurate per-scene audio timings for the webapp player
        t = narration.hook_dur if story.hook_image_path and narration.hook_dur else 0.0
        scene_timings = []
        for idx, (sc, dur) in enumerate(zip(story.scenes, narration.scene_durations or [])):
            extra = narration.silence_between if idx < len(story.scenes) - 1 else narration.outro_dur + 0.3
            scene_timings.append({"index": sc.index, "start": round(t, 4), "end": round(t + dur + extra, 4)})
            t += dur + extra
        import json as _json
        (self.out_dir / "timings.json").write_text(
            _json.dumps({"scene_timings": scene_timings}, indent=2)
        )

        print(f"  Saved: {video_path}")
        return VideoPackage(video_path=str(video_path), thumbnail_path=str(thumb_path), duration_seconds=audio_dur)


class TikTokAgent(Agent):
    BASE_URL = "https://open.tiktokapis.com"

    def __init__(self, access_token: str):
        super().__init__("tiktok_agent")
        self.access_token = access_token

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        }

    def query_creator_info(self) -> Dict[str, Any]:
        url = f"{self.BASE_URL}/v2/post/publish/creator_info/query/"
        r = requests.post(url, headers=self._headers(), json={})
        r.raise_for_status()
        return r.json()

    def init_direct_post(self, title: str, video_path: str, privacy_level: str = "SELF_ONLY") -> Dict[str, Any]:
        file_size = Path(video_path).stat().st_size
        payload = {
            "post_info": {
                "title": title,
                "privacy_level": privacy_level,
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
                "video_cover_timestamp_ms": 1000,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": file_size,
                "chunk_size": file_size,
                "total_chunk_count": 1,
            },
        }
        url = f"{self.BASE_URL}/v2/post/publish/video/init/"
        r = requests.post(url, headers=self._headers(), json=payload)
        r.raise_for_status()
        return r.json()

    def init_upload_draft(self, video_path: str) -> Dict[str, Any]:
        file_size = Path(video_path).stat().st_size
        payload = {
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": file_size,
                "chunk_size": file_size,
                "total_chunk_count": 1,
            }
        }
        url = f"{self.BASE_URL}/v2/post/publish/inbox/video/init/"
        r = requests.post(url, headers=self._headers(), json=payload)
        r.raise_for_status()
        return r.json()

    def upload_binary(self, upload_url: str, video_path: str) -> None:
        data = Path(video_path).read_bytes()
        headers = {
            "Content-Type": "video/mp4",
            "Content-Length": str(len(data)),
            "Content-Range": f"bytes 0-{len(data)-1}/{len(data)}",
        }
        r = requests.put(upload_url, headers=headers, data=data)
        r.raise_for_status()

    def fetch_status(self, publish_id: str) -> Dict[str, Any]:
        url = f"{self.BASE_URL}/v2/post/publish/status/fetch/"
        r = requests.post(url, headers=self._headers(), json={"publish_id": publish_id})
        r.raise_for_status()
        return r.json()


class QAAgent(Agent):
    def __init__(self):
        super().__init__("qa_agent")

    def run(self, story: StoryPackage, narration: NarrationPackage, video: VideoPackage) -> Dict[str, Any]:
        issues = []
        if len(story.scenes) < 5:
            issues.append("Too few scenes for good retention.")
        if not story.hook:
            issues.append("Missing hook.")
        if not narration.subtitles_path:
            issues.append("Missing subtitles.")
        if not video.video_path:
            issues.append("Missing video.")
        return {"ok": len(issues) == 0, "issues": issues}


class MoralStoryPipeline:
    def __init__(self, workdir: str, tiktok_access_token: str = "", reference_image_path: str = ""):
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.story_agent = StoryAgent()
        self.prompt_agent = PromptConsistencyAgent()
        self.image_agent = ImageAgent(self.workdir / "images", reference_image_path or None)
        elevenlabs_key = os.getenv("ELEVENLABS_API_KEY", "")
        _voices = [v.strip() for v in os.getenv("ELEVENLABS_VOICE_IDS", "").split(",") if v.strip()]
        if not _voices:
            _voices = [v.strip() for v in os.getenv("ELEVENLABS_VOICE_ID", "").split(",") if v.strip()]
        elevenlabs_voice = random.choice(_voices) if _voices else ""
        print(f"Voice: {elevenlabs_voice}")
        self.narration_agent = NarrationAgent(self.workdir / "audio", elevenlabs_key, elevenlabs_voice)
        self.video_agent = VideoAgent(self.workdir / "video")
        self.qa_agent = QAAgent()
        self.tiktok_agent = TikTokAgent(tiktok_access_token) if tiktok_access_token else None

    def run(self, idea: StoryIdea, upload_mode: Optional[str] = None) -> Dict[str, Any]:
        story = self.story_agent.run(idea)
        story = self.prompt_agent.run(story)
        story = self.image_agent.run(story)
        narration = self.narration_agent.run(story)
        video = self.video_agent.run(story, narration)
        qa = self.qa_agent.run(story, narration, video)

        result = {
            "story": asdict(story),
            "narration": asdict(narration),
            "video": asdict(video),
            "qa": qa,
        }

        if upload_mode and self.tiktok_agent and qa["ok"]:
            result["creator_info"] = self.tiktok_agent.query_creator_info()
            caption = f"{story.title} | {story.moral} {' '.join(story.hashtags)}"
            if upload_mode == "direct_post":
                init = self.tiktok_agent.init_direct_post(caption[:2200], video.video_path)
            elif upload_mode == "draft":
                init = self.tiktok_agent.init_upload_draft(video.video_path)
            else:
                raise ValueError("upload_mode must be 'direct_post' or 'draft'")
            result["tiktok_init"] = init
            upload_url = init.get("data", {}).get("upload_url")
            publish_id = init.get("data", {}).get("publish_id")
            if upload_url:
                self.tiktok_agent.upload_binary(upload_url, video.video_path)
            if publish_id:
                result["tiktok_status"] = self.tiktok_agent.fetch_status(publish_id)

        return result


def _load_env(path: str = ".env") -> None:
    """Simple .env loader — no extra dependencies needed."""
    env_file = Path(path)
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


if __name__ == "__main__":
    import datetime
    _load_env()
    token = os.getenv("TIKTOK_ACCESS_TOKEN", "")
    date_str = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    workdir = f"./out/{date_str}"
    ref_image = os.getenv("REFERENCE_IMAGE", f"{workdir}/images/scene_01.png")
    pipeline = MoralStoryPipeline(workdir=workdir, tiktok_access_token=token, reference_image_path=ref_image)
    idea = StoryIdea(topic="gratitude and saying thank you", moral="Gratitude makes kindness grow.")
    result = pipeline.run(idea, upload_mode=None)
    print(json.dumps(result, indent=2))


# To authenticate with Hugging Face, run:
# python -c "from huggingface_hub import login; login(token=os.environ['HF_TOKEN'])"
