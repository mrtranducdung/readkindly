#!/usr/bin/env python3
"""
Generate an image from a text prompt using FLUX.1-schnell (local model).

Usage:
    python generate_image.py "a cute fox reading a book in a forest"
    python generate_image.py "a rabbit chef cooking soup" --output my_image.png
    python generate_image.py "a dragon flying over mountains" --width 576 --height 1024
"""

import argparse
import gc
from pathlib import Path


def generate_image(
    prompt: str,
    width: int = 576,
    height: int = 1024,
    num_inference_steps: int = 4,
    guidance_scale: float = 0.0,
    output_path: str | None = None,
) -> Path:
    import torch
    from diffusers import FluxPipeline

    print("Loading FLUX.1-schnell (this takes a minute on first run)...")
    pipe = FluxPipeline.from_pretrained(
        "black-forest-labs/FLUX.1-schnell",
        torch_dtype=torch.bfloat16,
    )

    try:
        pipe.enable_sequential_cpu_offload()
    except RuntimeError as exc:
        if "requires accelerator" not in str(exc):
            raise
        print("accelerate not installed; continuing without sequential CPU offload.")

    print(f"Prompt : {prompt}")
    print(f"Size   : {width}x{height}  steps={num_inference_steps}")
    print("Generating...", flush=True)

    result = pipe(
        prompt=prompt,
        height=height,
        width=width,
        num_inference_steps=num_inference_steps,
        guidance_scale=guidance_scale,
    )

    if output_path is None:
        safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in prompt[:40]).strip()
        output_path = f"{safe}.png"

    out = Path(output_path)
    result.images[0].save(str(out))
    print(f"Saved  : {out.resolve()}")

    # Free VRAM
    del pipe
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an image from a text prompt with FLUX.1-schnell")
    parser.add_argument("prompt", help="Text prompt describing the image")
    parser.add_argument("--output", "-o", help="Output file path (default: auto-named .png)")
    parser.add_argument("--width", "-W", type=int, default=576, help="Image width (default: 576)")
    parser.add_argument("--height", "-H", type=int, default=1024, help="Image height (default: 1024)")
    parser.add_argument("--steps", "-s", type=int, default=4, help="Inference steps (default: 4)")
    args = parser.parse_args()

    generate_image(
        prompt=args.prompt,
        width=args.width,
        height=args.height,
        num_inference_steps=args.steps,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
