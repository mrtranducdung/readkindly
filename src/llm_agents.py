from __future__ import annotations
import json
from mistralai.client.sdk import Mistral
from .config import MISTRAL_API_KEY, MODEL_NAME, THEME, AGE_RANGE, VIDEO_SECONDS, CHANNEL_NAME
from .schemas import StoryPack

SYSTEM_PROMPT = f"""
You are an agentic kids short-video studio for the channel "{CHANNEL_NAME}".
Audience: children age {AGE_RANGE}.
Theme: {THEME}.
Create one positive short moral story starring cute animal characters (e.g. a bunny, bear, fox, owl, or similar).
Keep the full video around {VIDEO_SECONDS} seconds.
Use exactly 10 scenes.
Keep language simple and safe.
Return a hook_visual_description for the opening image.
The hook image must show all major recurring characters together and clearly establish the story theme.
Each visual_description must describe the animal characters and setting in rich detail for a picture-book illustration.
Output valid JSON only.
""".strip()

USER_PROMPT = """
Return JSON with this schema:
{
  "topic": "string",
  "moral": "string",
  "age_range": "string",
  "title": "string",
  "hook": "string",
  "hook_visual_description": "string",
  "characters": [
    {
      "name": "string",
      "description": "string"
    }
  ],
  "scenes": [
    {
      "scene_number": 1,
      "title": "string",
      "narration": "string",
      "onscreen_text": "string",
      "visual_description": "string",
      "duration_seconds": 6
    }
  ],
  "caption": "string",
  "hashtags": ["#kids", "#goodhabits"]
}

Rules:
- Original story
- Bright, child-friendly visuals
- Short narration
- Short onscreen text
- Exactly 10 scenes numbered 1 through 10
- Keep the same named characters visually consistent across the hook image and every scene
- Total duration close to target
""".strip()

def build_client() -> Mistral:
    if not MISTRAL_API_KEY:
        raise RuntimeError("Missing MISTRAL_API_KEY in environment.")
    return Mistral(api_key=MISTRAL_API_KEY)

def generate_story_pack(theme: str = "") -> StoryPack:
    client = build_client()
    system = SYSTEM_PROMPT
    if theme:
        system = system + f"\n\nUser-requested theme: {theme}. Build the story around this theme."
    response = client.chat.complete(
        model=MODEL_NAME,
        temperature=0.9,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": USER_PROMPT},
        ],
    )
    data = json.loads(response.choices[0].message.content)
    return StoryPack.model_validate(data)
