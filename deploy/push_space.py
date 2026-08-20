"""Create (or update) the Hugging Face Space and upload the runtime files.

Prerequisite -- authenticate yourself first, so no token ever passes through
this script or the terminal history:

    hf auth login

Then:

    python deploy/push_space.py                 # push to <you>/orbital-sentinel
    python deploy/push_space.py --name my-space
    python deploy/push_space.py --private
    python deploy/push_space.py --dry-run       # list what would upload

Only what the app needs at runtime is uploaded. The raw JPL and GeoNames dumps
stay local: they are build-time inputs already reduced to three small caches.
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (source path relative to repo root, destination path in the Space)
INCLUDE_DIRS = [
    ("backend/app", "backend/app", (".py",)),
    ("backend/models", "backend/models", (".pkl", ".json")),
    ("frontend/js", "frontend/js", (".js",)),
    ("frontend/css", "frontend/css", (".css",)),
    ("frontend/vendor", "frontend/vendor", (".js",)),
    ("frontend/textures", "frontend/textures", (".jpg", ".png")),
]
INCLUDE_FILES = [
    ("Dockerfile", "Dockerfile"),
    ("backend/requirements.txt", "backend/requirements.txt"),
    ("frontend/index.html", "frontend/index.html"),
    ("backend/data/land_mask.npy", "backend/data/land_mask.npy"),
    ("backend/data/cities.npz", "backend/data/cities.npz"),
    ("backend/data/neo_index.json", "backend/data/neo_index.json"),
    ("deploy/space_readme.md", "README.md"),
]


def collect() -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    for src, dst in INCLUDE_FILES:
        p = os.path.join(ROOT, src)
        if os.path.exists(p):
            items.append((p, dst))
        else:
            print(f"  missing (skipped): {src}")

    for src_dir, dst_dir, exts in INCLUDE_DIRS:
        base = os.path.join(ROOT, src_dir)
        if not os.path.isdir(base):
            print(f"  missing (skipped): {src_dir}/")
            continue
        for cur, _dirs, files in os.walk(base):
            if "__pycache__" in cur:
                continue
            for f in sorted(files):
                if not f.endswith(exts):
                    continue
                full = os.path.join(cur, f)
                rel = os.path.relpath(full, base).replace(os.sep, "/")
                items.append((full, f"{dst_dir}/{rel}"))
    return items


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="orbital-sentinel")
    ap.add_argument("--private", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    items = collect()
    total = sum(os.path.getsize(p) for p, _ in items)
    print(f"{len(items)} files, {total / 1048576:.1f} MB")

    missing_models = not any(d.endswith(".pkl") for _, d in items)
    if missing_models:
        print("\nNo trained models found. The Space will still run the analytic\n"
              "physics, but the surrogate columns will be empty.\n"
              "Train first with: python app/train.py")

    if args.dry_run:
        for _p, d in items:
            print("   ", d)
        return 0

    try:
        from huggingface_hub import HfApi
    except ImportError:
        print("huggingface_hub is not installed:\n"
              "  pip install huggingface_hub", file=sys.stderr)
        return 1

    api = HfApi()
    try:
        who = api.whoami()
    except Exception:
        print("Not logged in to Hugging Face.\n"
              "Run this yourself so the token stays with you:\n\n"
              "    hf auth login\n", file=sys.stderr)
        return 1

    user = who["name"]
    repo_id = f"{user}/{args.name}"
    print(f"pushing to Space: {repo_id}")

    api.create_repo(repo_id=repo_id, repo_type="space", space_sdk="docker",
                    private=args.private, exist_ok=True)

    # Upload as one commit rather than file by file, so the Space rebuilds once.
    from huggingface_hub import CommitOperationAdd

    ops = [CommitOperationAdd(path_in_repo=dst, path_or_fileobj=src)
           for src, dst in items]
    api.create_commit(repo_id=repo_id, repo_type="space", operations=ops,
                      commit_message="Deploy Orbital Sentinel")

    print(f"\ndone -> https://huggingface.co/spaces/{repo_id}")
    print("The Space builds the Docker image now; first boot takes a few minutes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
