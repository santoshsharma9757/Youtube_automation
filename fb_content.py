"""
fb_content.py — Chintu Wonder World: Facebook Content Studio
=============================================================
Standalone CLI for creating and uploading Facebook Posts, Stories, and Reels.
Completely separate from the video automation pipeline.

COMMANDS:
─────────────────────────────────────────────────────────────────────────────
CREATE COMMANDS (generates content + saves locally):

  python fb_content.py create post --topic "Chintu ki nai kahani about sharing"
  python fb_content.py create story --topic "Aaj ki seekh: sach bolna chahiye"
  python fb_content.py create reel --topic "Jungle adventure" [--scenes 5]

STITCH COMMANDS (combine your images into a reel video):

  python fb_content.py stitch reel --folder input/fb_reels/my_images/
  python fb_content.py stitch reel  ← auto-finds all ready input folders

UPLOAD COMMANDS (publish to Facebook):

  python fb_content.py upload post   ← upload all pending posts
  python fb_content.py upload story  ← upload all pending stories
  python fb_content.py upload reel   ← upload all pending reels
  python fb_content.py upload all    ← upload everything pending

  python fb_content.py upload post --dir output/fb_content/posts/20260623_chintu.../
  python fb_content.py upload reel --force  ← re-upload even if already uploaded

LIST COMMAND (see what's ready):

  python fb_content.py list

─────────────────────────────────────────────────────────────────────────────
OUTPUT STRUCTURE:

  output/fb_content/
    posts/{date_slug}/
      image.png     ← DALL-E 3 generated Pixar-style image
      caption.txt   ← Full FB caption with Hindi text + hashtags
      metadata.json ← All structured data
      status.json   ← Upload status tracking

    stories/{date_slug}/
      story_card.png ← 1080×1920 story card (gradient + Hindi text)
      text.txt       ← Hook text
      metadata.json  ← All structured data
      status.json    ← Upload status tracking

    reels/{date_slug}/
      reel.mp4      ← Stitched slideshow reel video
      caption.txt   ← Reel caption
      metadata.json ← All structured data
      status.json   ← Upload status tracking

  input/fb_reels/{date_slug}/
      prompts.txt   ← Scene image prompts (fill these with images then stitch)
      caption.txt   ← Pre-generated caption
      metadata.json ← Reel plan data
      1.png, 2.png... ← YOUR images go here
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Force UTF-8 console output on Windows — prevents cp1252 UnicodeEncodeError
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from config import get_config, setup_logging

LOGGER = logging.getLogger(__name__)

FB_CONTENT_DIR = Path("output/fb_content")
FB_POSTS_DIR   = FB_CONTENT_DIR / "posts"
FB_STORIES_DIR = FB_CONTENT_DIR / "stories"
FB_REELS_DIR   = FB_CONTENT_DIR / "reels"
FB_REEL_INPUT  = Path("input/fb_reels")


# ── Safe print (handles Unicode on Windows console) ───────────────────────────

def safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        print(text.encode(enc, errors="replace").decode(enc))


# ═════════════════════════════════════════════════════════════════════════════
#  AUTO TOPIC PICKER
# ═════════════════════════════════════════════════════════════════════════════

def _pick_auto_topic() -> str:
    """
    Pick a random topic from STORY_TOPIC_BANK and format it as a rich topic string.
    Falls back to a simple random moral lesson if the bank is unavailable.
    """
    try:
        from story_topics import STORY_TOPIC_BANK
        import random
        entry = random.choice(STORY_TOPIC_BANK)
        title    = entry.get("title", "")
        moral_h  = entry.get("moral_hindi", "")
        moral_e  = entry.get("moral", "")
        kids_h   = entry.get("kids_hook", "")
        # Compose a rich topic string
        topic = title
        if moral_h:
            topic += f" — Seekh: {moral_h}"
        elif moral_e:
            topic += f" — Moral: {moral_e}"
        return topic
    except Exception:
        import random
        fallbacks = [
            "Sacchi dosti ka matlab kya hota hai",
            "Sach bolne ki himmat",
            "Maa ki mehnat ki kadr",
            "Sharing is caring — baantne mein sukh hai",
            "Mushkil mein himmat rakhna",
            "Bade logo ki izzat karna",
        ]
        return random.choice(fallbacks)


# ═════════════════════════════════════════════════════════════════════════════
#  CREATE commands
# ═════════════════════════════════════════════════════════════════════════════

def cmd_create_post(args: argparse.Namespace) -> None:
    """Create a Facebook post with AI caption + generated image."""
    topic = getattr(args, "topic", None) or ""
    if not topic:
        if getattr(args, "auto", False):
            topic = _pick_auto_topic()
            safe_print(f"\n🎲 Auto-topic selected: {topic}\n")
        else:
            safe_print("\u274c Provide --topic or use --auto to pick one automatically.")
            safe_print('   python fb_content.py create post --topic "Chintu aur jadui kitab"')
            safe_print('   python fb_content.py create post --auto')
            sys.exit(1)

    safe_print(f"\n🎨 Creating Facebook POST for topic: {topic}\n")
    from fb_post_creator import FBPostCreator
    config = get_config()
    creator = FBPostCreator(config)
    post_dir = creator.create(topic)
    safe_print(f"\n✅ Post created → {post_dir.resolve()}")

    if args.upload:
        safe_print("\n📤 Auto-uploading post to Facebook...")
        from fb_social_uploader import FBSocialUploader
        uploader = FBSocialUploader(config)
        result = uploader.upload_post_dir(post_dir)
        safe_print(f"✅ Uploaded! ID: {result.get('id')}")


def cmd_create_story(args: argparse.Namespace) -> None:
    """Create a Facebook Story card."""
    topic = getattr(args, "topic", None) or ""
    if not topic:
        if getattr(args, "auto", False):
            topic = _pick_auto_topic()
            safe_print(f"\n🎲 Auto-topic selected: {topic}\n")
        else:
            safe_print("❌ Provide --topic or use --auto to pick one automatically.")
            safe_print('   python fb_content.py create story --topic "Aaj ki seekh"')
            safe_print('   python fb_content.py create story --auto')
            sys.exit(1)

    safe_print(f"\n📱 Creating Facebook STORY for topic: {topic}\n")
    from fb_story_creator import FBStoryCreator
    config = get_config()
    creator = FBStoryCreator(config)
    story_dir = creator.create(topic)
    safe_print(f"\n✅ Story card created → {story_dir.resolve()}")

    if args.upload:
        safe_print("\n📤 Auto-uploading story to Facebook...")
        from fb_social_uploader import FBSocialUploader
        uploader = FBSocialUploader(config)
        result = uploader.upload_story_dir(story_dir)
        safe_print(f"✅ Uploaded! ID: {result.get('id')}")


# (Reels are handled by main.py)


# ═════════════════════════════════════════════════════════════════════════════
#  UPLOAD commands
# ═════════════════════════════════════════════════════════════════════════════

def cmd_upload(args: argparse.Namespace) -> None:
    """Upload pending content to Facebook."""
    from fb_social_uploader import FBSocialUploader
    config = get_config()
    uploader = FBSocialUploader(config)

    content_type = args.content_type  # post | story | reel | all
    force = getattr(args, "force", False)

    # Upload a specific directory if --dir is given
    if hasattr(args, "dir") and args.dir:
        specific_dir = Path(args.dir)
        if not specific_dir.exists():
            safe_print(f"❌ Directory not found: {specific_dir}")
            sys.exit(1)

        if content_type == "post":
            result = uploader.upload_post_dir(specific_dir)
        elif content_type == "story":
            result = uploader.upload_story_dir(specific_dir)
        else:
            safe_print("❌ Cannot use --dir with 'upload all'. Specify post/story/reel.")
            sys.exit(1)

        safe_print(f"\n✅ Uploaded! Result: {result}")
        return

    # Upload all pending of given type
    safe_print(f"\n📤 Uploading all pending {content_type}s to Facebook...\n")
    results = uploader.upload_all_pending(content_type=content_type, force=force)

    total = sum(len(v) for v in results.values())
    safe_print(f"\n🎉 Done! {total} item(s) uploaded.")
    for k, v in results.items():
        if v:
            safe_print(f"   {k.capitalize()}: {len(v)} uploaded")


# ═════════════════════════════════════════════════════════════════════════════
#  LIST command
# ═════════════════════════════════════════════════════════════════════════════

def cmd_list(args: argparse.Namespace) -> None:
    """List all content and their upload status."""
    safe_print("\n" + "═" * 70)
    safe_print("  CHINTU WONDER WORLD — Facebook Content Studio")
    safe_print("═" * 70)

    _list_content_dir(FB_POSTS_DIR,   "📝 PENDING FB POSTS",   "caption.txt",    "image.png")
    _list_content_dir(FB_STORIES_DIR, "📱 PENDING FB STORIES",  "text.txt",       "story_card.png")
    _list_youtube_community()

    safe_print("\n" + "═" * 70)


def _list_youtube_community() -> None:
    from config import YOUTUBE_COMMUNITY_DIR
    safe_print("\n🔴 YOUTUBE COMMUNITY POSTS (Pending Manual Upload):")
    safe_print("─" * 70)
    if not YOUTUBE_COMMUNITY_DIR.exists():
        safe_print("  (none)")
        return
    folders = sorted(YOUTUBE_COMMUNITY_DIR.iterdir(), reverse=True)
    if not folders:
        safe_print("  (none)")
        return
    for folder in folders:
        if not folder.is_dir():
            continue
        has_img = (folder / "image.png").exists() or (folder / "image.jpg").exists()
        img_icon = "🖼️" if has_img else "❌"
        safe_print(f"  ⏳ {img_icon}  {folder.name}")


def _list_content_dir(dir_path: Path, label: str, text_file: str, media_file: str) -> None:
    safe_print(f"\n{label}:")
    safe_print("─" * 70)
    if not dir_path.exists():
        safe_print("  (none)")
        return
    folders = sorted(dir_path.iterdir(), reverse=True)
    if not folders:
        safe_print("  (none)")
        return
    for folder in folders:
        if not folder.is_dir():
            continue
        status_file = folder / "status.json"
        status = "⬜ pending"
        if status_file.exists():
            s = json.loads(status_file.read_text(encoding="utf-8"))
            status = "✅ uploaded" if s.get("uploaded") else "⬜ pending"
        has_media = (folder / media_file).exists()
        media_icon = "🖼️" if has_media else "❌"
        safe_print(f"  {status}  {media_icon}  {folder.name}")


# ═════════════════════════════════════════════════════════════════════════════
#  CLI Parser
# ═════════════════════════════════════════════════════════════════════════════

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fb_content.py",
        description=(
            "Wonder Stories TV — Facebook Content Studio\n"
            "Create and upload Posts and Stories to Facebook.\n\n"
            "Examples:\n"
            '  python fb_content.py create post --topic "Chintu ki nai kahani"\n'
            '  python fb_content.py create story --topic "Aaj ki seekh"\n'
            "  python fb_content.py upload all\n"
            "  python fb_content.py list\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # ── create ────────────────────────────────────────────────────────────────
    create_p = subparsers.add_parser("create", help="Create new content (post/story)")
    create_sub = create_p.add_subparsers(dest="content_type", required=True)

    # create post
    cp = create_sub.add_parser("post", help="Create a Facebook post (AI caption + image)")
    cp.add_argument("--topic", required=False, default="",
                    help="The topic/idea for the post (Hindi or English). Skip to use --auto.")
    cp.add_argument("--auto", action="store_true",
                    help="Auto-pick a topic from the story bank (no --topic needed)")
    cp.add_argument("--upload", action="store_true",
                    help="Immediately upload to Facebook after creating")

    # create story
    cs = create_sub.add_parser("story", help="Create a Facebook Story card")
    cs.add_argument("--topic", required=False, default="",
                    help="The topic/idea for the story. Skip to use --auto.")
    cs.add_argument("--auto", action="store_true",
                    help="Auto-pick a topic from the story bank (no --topic needed)")
    cs.add_argument("--upload", action="store_true",
                    help="Immediately upload to Facebook after creating")

    # ── upload ────────────────────────────────────────────────────────────────
    upload_p = subparsers.add_parser("upload", help="Upload pending content to Facebook")
    upload_p.add_argument(
        "content_type",
        choices=["post", "story", "all"],
        help="What to upload: post | story | all",
    )
    upload_p.add_argument("--dir", type=str, default=None,
                          help="Upload a specific content directory")
    upload_p.add_argument("--force", action="store_true",
                          help="Re-upload even if already marked as uploaded")

    # ── list ──────────────────────────────────────────────────────────────────
    subparsers.add_parser("list", help="List all content and upload status")

    return parser


# ═════════════════════════════════════════════════════════════════════════════
#  Main
# ═════════════════════════════════════════════════════════════════════════════

def main() -> None:
    setup_logging()
    parser = build_parser()
    args = parser.parse_args()

    safe_print("\n" + "─" * 60)
    safe_print("  🌟 Chintu Wonder World — Facebook Content Studio")
    safe_print("─" * 60 + "\n")

    if args.command == "create":
        if args.content_type == "post":
            cmd_create_post(args)
        elif args.content_type == "story":
            cmd_create_story(args)

    elif args.command == "upload":
        cmd_upload(args)

    elif args.command == "list":
        cmd_list(args)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
