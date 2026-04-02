"""Quick test: assemble video from already-generated images and audio."""
from pathlib import Path
from genstory import (
    StoryPackage, Scene, NarrationPackage, VideoAgent
)

scenes = [
    Scene(1,  "Morning",       "Lumi woke up in the sunny forest, ready for adventure.",                   "A happy new day!",        "", 4.0,  "out/images/scene_01.png"),
    Scene(2,  "Bird Helps",    "A tiny bird helped Lumi find sweet berries for breakfast.",                "A friend helped him.",    "", 5.0,  "out/images/scene_02.png"),
    Scene(3,  "Forgot",        "Lumi smiled and ran off so fast that he forgot to say thank you.",         "He forgot to say thanks...","", 5.0, "out/images/scene_03.png"),
    Scene(4,  "Rabbit Helps",  "Later, a rabbit helped him cross the river safely.",                       "Another friend helped him.","", 5.0,"out/images/scene_04.png"),
    Scene(5,  "Forgot Again",  "But once again, Lumi forgot to say thank you.",                            "He forgot again.",         "", 4.5, "out/images/scene_05.png"),
    Scene(6,  "Lonely",        "Soon, Lumi noticed that no one came to help him anymore.",                 "Why is everyone gone?",    "", 5.0, "out/images/scene_06.png"),
    Scene(7,  "Realization",   "Then Lumi stopped and thought, Oh no, I forgot to thank my friends.",     "Oh no!",                   "", 5.0, "out/images/scene_07.png"),
    Scene(8,  "Apology",       "He ran back and said, Thank you for helping me. I am sorry I forgot.",    "Thank you. I am sorry.",   "", 6.0, "out/images/scene_08.png"),
    Scene(9,  "Joy Returns",   "The bird chirped, the rabbit smiled, and the forest felt bright again.",   "Kindness came back.",      "", 5.5, "out/images/scene_09.png"),
    Scene(10, "Moral",         "Lumi learned that saying thank you makes kindness grow everywhere.",       "Say thank you.",           "", 6.0, "out/images/scene_10.png"),
]

story = StoryPackage(
    title="Lumi and the Magic of Thank You",
    hook="What happens when you forget to say thank you?",
    moral="Gratitude makes kindness grow.",
    scenes=scenes,
    outro="Always say thank you. Kindness grows when gratitude grows.",
)

narration = NarrationPackage(
    full_script="",
    audio_path="out/audio/narration.mp3",
    subtitles_path="out/audio/captions.srt",
    scene_durations=[],  # empty = will be estimated from total audio duration
)

agent = VideoAgent(Path("out/video"))
result = agent.run(story, narration)
print(f"Done! Video: {result.video_path}  ({result.duration_seconds:.1f}s)")
