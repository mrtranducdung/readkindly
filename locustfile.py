"""
Load test for readkindly.onrender.com

Usage:
    pip install locust
    locust --host https://readkindly.onrender.com
    # then open http://localhost:8089

Or headless (no UI):
    locust --host https://readkindly.onrender.com --headless -u 50 -r 5 --run-time 2m
"""
import random
from locust import HttpUser, between, task, events


# Populated once at test start from /api/stories so we use real IDs
_story_ids: list[str] = []
_story_scene_counts: dict[str, int] = {}


@events.test_start.add_listener
def fetch_stories(environment, **kwargs):
    """Pre-load story IDs so tasks can reference real content."""
    host = environment.host.rstrip("/")
    import urllib.request, json
    try:
        with urllib.request.urlopen(f"{host}/api/stories", timeout=15) as r:
            stories = json.loads(r.read())
        for s in stories:
            sid = s.get("id")
            if sid:
                _story_ids.append(sid)
                _story_scene_counts[sid] = len(s.get("scenes", []))
        print(f"\n✓ Loaded {len(_story_ids)} stories for testing\n")
    except Exception as e:
        print(f"\n⚠ Could not pre-fetch stories: {e} — tasks will skip story detail requests\n")


class StoryReader(HttpUser):
    """
    Simulates a regular visitor:
      - Browses the story list
      - Opens a story and reads it scene by scene (images + audio)
    """
    wait_time = between(1, 4)

    def _random_story(self):
        return random.choice(_story_ids) if _story_ids else None

    @task(4)
    def homepage(self):
        self.client.get("/", name="/ (homepage)")

    @task(5)
    def list_stories(self):
        self.client.get("/api/stories", name="/api/stories")

    @task(8)
    def read_story_flow(self):
        """Full read: story metadata → hook image → hook audio → scenes."""
        story_id = self._random_story()
        if not story_id:
            return

        with self.client.get(
            f"/api/stories/{story_id}",
            name="/api/stories/[id]",
            catch_response=True,
        ) as r:
            if r.status_code == 404:
                r.success()  # story may have been deleted, not a failure
                return

        # Hook image + audio
        self.client.get(
            f"/api/stories/{story_id}/image/hook",
            name="/api/stories/[id]/image/hook",
        )
        self.client.get(
            f"/api/stories/{story_id}/audio/hook",
            name="/api/stories/[id]/audio/hook",
        )

        # Read 1–3 random scenes (users don't always finish)
        scene_count = _story_scene_counts.get(story_id, 5)
        scenes_to_read = random.sample(
            range(1, scene_count + 1),
            k=min(random.randint(1, 3), scene_count),
        )
        for n in scenes_to_read:
            self.client.get(
                f"/api/stories/{story_id}/image/{n}",
                name="/api/stories/[id]/image/[n]",
            )
            self.client.get(
                f"/api/stories/{story_id}/audio/{n}",
                name="/api/stories/[id]/audio/[n]",
            )

    @task(2)
    def outro_audio(self):
        story_id = self._random_story()
        if not story_id:
            return
        self.client.get(
            f"/api/stories/{story_id}/audio/outro",
            name="/api/stories/[id]/audio/outro",
        )

    @task(1)
    def static_pages(self):
        self.client.get(random.choice(["/tos", "/privacy"]), name="/tos or /privacy")


class HeavyReader(HttpUser):
    """
    Simulates a user who finishes the whole story (all scenes in order).
    Fewer of these — weight kept low.
    """
    wait_time = between(3, 8)
    weight = 1  # 1 HeavyReader per ~3 StoryReaders

    def _random_story(self):
        return random.choice(_story_ids) if _story_ids else None

    @task
    def read_full_story(self):
        story_id = self._random_story()
        if not story_id:
            return

        self.client.get(f"/api/stories/{story_id}", name="/api/stories/[id]")
        self.client.get(f"/api/stories/{story_id}/image/hook", name="/api/stories/[id]/image/hook")
        self.client.get(f"/api/stories/{story_id}/audio/hook", name="/api/stories/[id]/audio/hook")

        scene_count = _story_scene_counts.get(story_id, 5)
        for n in range(1, scene_count + 1):
            self.client.get(f"/api/stories/{story_id}/image/{n}", name="/api/stories/[id]/image/[n]")
            self.client.get(f"/api/stories/{story_id}/audio/{n}", name="/api/stories/[id]/audio/[n]")

        self.client.get(f"/api/stories/{story_id}/audio/outro", name="/api/stories/[id]/audio/outro")
