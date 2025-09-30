import os
import yaml
import hashlib
import requests
from pathlib import Path
from django.conf import settings
from .models import Library, MediaItem, FolderItem, Collection
from django.utils.text import slugify
import threading
from urllib.parse import quote
from PIL import Image
import subprocess
from .util import genres_dict
from django_q.tasks import async_task
import re
import logging

_scan_lock = threading.Lock()
logger = logging.getLogger(__name__)

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

def tmdb_fetch(title, year):
    api_key = settings.TMDB_API_KEY
    if not api_key:
        return None
    
    try:
        r = requests.get(
            'https://api.themoviedb.org/3/search/movie',
            params={
                'query': quote(title),
                'include_adult': True, 
                'language': 'en', 
                'page': 1,
                'year': year,
                'api_key': api_key
                },
            headers={'accept': 'application/json'},
            timeout=10
        )
        data = r.json()
        if data["total_results"] < 1:
            return None
        data = data["results"][0]
        otitle = data.get('original_title', title)
        poster_path = data.get('poster_path')
        backdrop_path = data.get('backdrop_path')
        poster_url = "https://image.tmdb.org/t/p/w500" + poster_path if poster_path else None
        backdrop_url = "https://image.tmdb.org/t/p/original" + backdrop_path if backdrop_path else poster_url

        description = data.get('overview')

        genre_ids = data.get('genre_ids')
        id = data.get('id')

        genres = []
        for gid in genre_ids:
            genres.append(genres_dict[gid])

        r = requests.get(
            f"https://api.themoviedb.org/3/movie/{id}",
            params={"api_key": api_key, "language": "en"},
            headers={'accept': 'application/json'},
            timeout=10
        )
        details = r.json()

        collection = details.get('belongs_to_collection')

        return {
            "title": otitle, 
            "poster_url": poster_url, 
            "backdrop_url": backdrop_url, 
            "description": description,
            "genres": genres,
            "id": id,
            "collection": collection,
        }
    except Exception:
        return None

def tmdb_get(id):
    media_item = MediaItem.objects.get(id=id)
    # fetch TMDB
    tmdb = tmdb_fetch(media_item.title, media_item.year)

    if tmdb:

        c = tmdb["collection"]

        if c:
            collection, _ = Collection.objects.get_or_create(
                tmdb_id=c["id"],
                defaults={"name": c["name"]}
            )
        else:
            collection = None

        media_item.collection = collection
        media_item.title = tmdb["title"]
        media_item.description = tmdb["description"]
        media_item.genre = tmdb["genres"]
        media_item.tmdb_id = tmdb["id"]

        # either backdrop has its own url, or its the poster_url so this is ok
        if tmdb.get("poster_url") and tmdb["poster_url"] != "N/A":

            movie_hash = file_hash(media_item.file_path)
            poster_cache = f"{movie_hash}.jpg"
            poster_path = settings.POSTER_DIR / poster_cache
            backdrop_cache = f"{movie_hash}.jpg"
            backdrop_path = settings.BACKDROP_DIR / backdrop_cache

            store_image(poster_path, tmdb["poster_url"])
            store_image(backdrop_path, tmdb["backdrop_url"])
            
            media_item.poster = poster_cache
            media_item.backdrop = backdrop_cache
        media_item.save()

def get_first_image(folder_path):
    for root, dirs, files in os.walk(folder_path):
        for f in files:
            if f.lower().endswith((".jpg", ".jpeg", ".png", "webp")):
                return os.path.join(root, f)
    return None


def get_image_size(path):
    try:
        with Image.open(path) as img:
            return img.width, img.height
    except Exception:
        return None, None

def store_image(path, url):
    if not path.exists():
        try:
            resp = requests.get(url, stream=True, timeout=20)
            if resp.status_code == 200:
                with open(path, "wb") as fh:
                    for chunk in resp.iter_content(1024):
                        fh.write(chunk)
        except Exception:
            pass

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

                if not MediaItem.objects.filter(file_path = full_path).exists():
                    ext = os.path.splitext(entry.name)[-1].lower()
                    if ext not in ALLOWED_VIDEO_EXTS | ALLOWED_IMAGE_EXTS:
                        continue

                    is_video = ext in ALLOWED_VIDEO_EXTS
                    width, height = get_image_size(full_path)
                    size = os.path.getsize(full_path)

                    name = os.path.splitext(entry.name)[0]
                    name = name.replace("-", " ").replace("_", " ").strip()

                    match = re.search(r"(.*)\b(\d{4})$", name)
                    if match:
                        title = match.group(1).strip()
                        year = int(match.group(2))
                    else:
                        title = name.strip()
                        year = None

                    media_item, _ = MediaItem.objects.update_or_create(
                        file_path=full_path,
                        library=library,
                        folder=folder_item,
                        width=width,
                        height=height,
                        file_size=size,
                        defaults={
                            "title": title,
                            "year": year,
                            "poster": None,
                            "is_video": is_video,
                            "ext": ext
                        }
                    )
                else:
                    media_item = MediaItem.objects.get(file_path = full_path)
                
                if media_item.library.sync and media_item.is_video and media_item.poster == None:
                    async_task("mediahub.scanner.tmdb_get", media_item.id)


def scan_once():
    _scan_lock.acquire()

    cfg = load_config()
    libraries = cfg.get("libraries", [])

    library_names = set(lib["name"] for lib in libraries)

    for db_lib in Library.objects.all():
        if db_lib.name not in library_names:
            print(f"Removing library {db_lib.name} (not in config)")
            db_lib.delete()

    for item in MediaItem.objects.all():
        if not os.path.exists(item.file_path):
            print(f"File removed, deleting {item.file_path}")
            item.delete()
        
    for folder in FolderItem.objects.all():
        if not os.path.exists(folder.path):
            print(f"Folder removed, deleting {folder.path}")
            folder.delete()

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

    _scan_lock.release()

def scan_once_safe():
    lock = _scan_lock.locked()

    if not lock:
        async_task("mediahub.scanner.scan_once")

    return lock

def capture_frame(video_path, output_path, time="00:00:05"):
    """Capture a frame at 5 seconds (default)"""
    subprocess.run([
        "ffmpeg", "-y", "-ss", time, "-i", video_path,
        "-vframes", "1", "-q:v", "2", str(output_path)
    ], check=True)

def get_preview(path):
    # For videos → extract frame with ffmpeg
    thumb_path = settings.CACHE_DIR / f"preview_{os.path.basename(path)}.jpg"
    
    if not thumb_path.exists():
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", path, "-ss", "00:00:02.000", "-vframes", "1", str(thumb_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            return None
    
    return thumb_path