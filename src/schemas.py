from __future__ import annotations
from pydantic import BaseModel, Field
from typing import List

class Character(BaseModel):
    name: str
    description: str

class Scene(BaseModel):
    scene_number: int = Field(..., ge=1)
    title: str
    narration: str
    onscreen_text: str
    visual_description: str
    duration_seconds: int = Field(default=5, ge=3, le=10)

class StoryPack(BaseModel):
    topic: str
    moral: str
    age_range: str
    title: str
    hook: str
    hook_visual_description: str
    characters: List[Character]
    scenes: List[Scene]
    caption: str
    hashtags: List[str]
