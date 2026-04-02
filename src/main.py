from __future__ import annotations
from .config import OUTPUT_DIR
from .llm_agents import generate_story_pack
from .visuals import create_all_scenes
from .audio import build_narration_text, generate_tts
from .subtitles import write_srt
from .video import render_video
from .utils import make_run_dir, save_json

def main() -> None:
    run_dir = make_run_dir(OUTPUT_DIR)
    print(f"[1/6] Generating story pack in {run_dir} ...")
    story_pack = generate_story_pack()
    save_json(run_dir / "story.json", story_pack)
    save_json(run_dir / "script.json", {
        "hook": story_pack.hook,
        "scenes": [s.model_dump() for s in story_pack.scenes],
        "moral": story_pack.moral,
    })

    caption = story_pack.caption.strip() + "\n" + " ".join(story_pack.hashtags)
    (run_dir / "caption.txt").write_text(caption, encoding="utf-8")

    print("[2/6] Creating scene visuals ...")
    scene_paths = create_all_scenes(story_pack, run_dir)

    print("[3/6] Generating narration audio ...")
    narration_path = run_dir / "narration.mp3"
    narration_text = build_narration_text(story_pack)
    (run_dir / "narration.txt").write_text(narration_text, encoding="utf-8")
    generate_tts(narration_text, narration_path)

    print("[4/6] Creating subtitles ...")
    write_srt(story_pack, run_dir / "subtitles.srt")

    print("[5/6] Rendering video ...")
    render_video(scene_paths, story_pack, narration_path, run_dir / "video.mp4")

    print("[6/6] Done")
    print(f"Video: {run_dir / 'video.mp4'}")
    print(f"Caption: {run_dir / 'caption.txt'}")

if __name__ == "__main__":
    main()
