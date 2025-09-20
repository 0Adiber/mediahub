import os
import yaml
import hashlib
import requests
from pathlib import Path
from django.conf import settings
from .models import Library, MediaItem, FolderItem
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

def get_first_image(folder_path):
    for root, dirs, files in os.walk(folder_path):
        for f in files:
            if f.lower().endswith((".jpg", ".jpeg", ".png")):
                return os.path.join(root, f)
    return None

def scan_folder(library, path, parent_folder=None):
    """
    Recursively scan a folder, create FolderItem and MediaItem objects.
    :param library: Library instance
    :param path: absolute path of the folder to scan
    :param parent_folder: FolderItem instance of parent folder (None for root)
    """

    if path != library.path:
        folder_name = os.path.basename(path.rstrip("/")) or path  # handle root
        poster = get_first_image(path)  # your function to get first image
        folder_item, _ = FolderItem.objects.update_or_create(
            library=library,
            parent=parent_folder,
            path=path,
            defaults={
                "name": folder_name,
                "poster": poster
            }
        )
    else:
        folder_item = None

    # Scan directory
    with os.scandir(path) as it:
        for entry in it:
            full_path = entry.path
            if entry.is_dir():
                # Recursively scan subfolder
                scan_folder(library, full_path, parent_folder=folder_item)
            elif entry.is_file():
                ext = os.path.splitext(entry.name)[-1].lower()
                if ext not in ALLOWED_VIDEO_EXTS | ALLOWED_IMAGE_EXTS:
                    continue

                is_video = ext in ALLOWED_VIDEO_EXTS

                media_item, _ = MediaItem.objects.update_or_create(
                    file_path=full_path,
                    library=library,
                    folder=folder_item,
                    defaults={
                        "title": os.path.splitext(entry.name)[0],
                        "poster": None,
                        "is_video": is_video,
                        "ext": ext
                    }
                )

                # fetch OMDB poster if needed
                if library.sync and is_video:
                    omdb = omdb_fetch(media_item.title)
                    if omdb:
                        media_item.title = omdb["title"]
                        if omdb.get("poster_url") and omdb["poster_url"] != "N/A":
                            poster_cache = f"{file_hash(full_path)}.jpg"
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
                            media_item.poster = poster_cache
                        media_item.save()


def scan_once():
    cfg = load_config()
    libraries = cfg.get("libraries", [])

    library_names = set(lib["name"] for lib in libraries)

    for db_lib in Library.objects.all():
        if db_lib.name not in library_names:
            print(f"Removing library {db_lib.name} (not in config)")
            db_lib.delete()

    for lib in libraries:
        lib_slug = slugify(lib["name"])
        library, _ = Library.objects.update_or_create(
            slug=lib_slug,
            defaults={
                "name": lib["name"],
                "path": lib["path"],
                "hidden": lib.get("hidden", False),
                "sync": lib.get("sync", False),
                "type": lib.get("type", "other")
            },
        )

        scan_folder(library, library.path, parent_folder=None)
