import os
import yaml
import hashlib
import requests
from pathlib import Path
from django.conf import settings
from .models import Library, MediaItem
from django.utils.text import slugify

ALLOWED_VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov"}
ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

def load_config():
    cfg_path = settings.BASE_DIR / "config.yaml"
    with open(cfg_path, "r") as f:
        return yaml.safe_load(f)

def file_hash(path):
    h = hashlib.sha1()
    h.update(str(path).encode())
    h.update(str(os.path.getmtime(path)).encode())
    return h.hexdigest()

def omdb_fetch(title):
    api_key = settings.OMDB_API_KEY
    if not api_key:
        return None
    try:
        r = requests.get(
            "http://www.omdbapi.com/",
            params={"apikey": api_key, "t": title},
            timeout=10,
        )
        data = r.json()
        if data.get("Response") == "True":
            return {"title": data.get("Title", title), "poster_url": data.get("Poster")}
    except Exception:
        return None
    return None

def scan_once():
    cfg = load_config()
    libraries = cfg.get("libraries", [])
    for lib in libraries:
        lib_slug = slugify(lib["name"])
        library, _ = Library.objects.update_or_create(
            slug=lib_slug,
            defaults={
                "name": lib["name"],
                "path": lib["path"],
                "hidden": lib.get("hidden", False),
                "sync": lib.get("sync", False),
            },
        )

        for root, dirs, files in os.walk(library.path):
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in ALLOWED_VIDEO_EXTS | ALLOWED_IMAGE_EXTS:
                    continue
                abs_path = os.path.join(root, fname)
                is_video = ext in ALLOWED_VIDEO_EXTS
                item, _ = MediaItem.objects.update_or_create(
                    file_path=abs_path,
                    library=library,
                    defaults={
                        "title": os.path.splitext(fname)[0],
                        "poster": None,
                        "is_video": is_video,
                        "ext": ext,
                    },
                )

                if library.sync and is_video:
                    omdb = omdb_fetch(item.title)
                    if omdb:
                        item.title = omdb["title"]
                        if omdb["poster_url"] and omdb["poster_url"] != "N/A":
                            poster_cache = f"{file_hash(abs_path)}.jpg"
                            poster_path = settings.POSTER_DIR / poster_cache
                            if not poster_path.exists():
                                try:
                                    resp = requests.get(omdb["poster_url"], stream=True, timeout=20)
                                    if resp.status_code == 200:
                                        with open(poster_path, "wb") as fh:
                                            for chunk in resp.iter_content(1024):
                                                fh.write(chunk)
                                except Exception:
                                    pass
                            item.poster = poster_cache
                        item.save()
