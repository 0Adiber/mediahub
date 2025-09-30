from django.shortcuts import render, redirect, get_object_or_404
from django.http import StreamingHttpResponse, Http404, FileResponse, JsonResponse
from .models import Library, MediaItem, FolderItem, PlaybackProgress, Collection
from .scanner import scan_once_safe, load_config, get_preview
from .subtitles import get_or_fetch
import os, mimetypes, subprocess
from wsgiref.util import FileWrapper
from django.conf import settings
from django.db.models import Q
from urllib.parse import quote, unquote
import json
from random import sample

def posterize(media_items):
    for it in media_items:
        if it.poster:
            it.poster_url = "/static_cache/posters/" + it.poster
        else:
            it.poster_url = "/static/images/mediahub-placeholder.jpg"

        it.viewer_url = f"/media/player/?path={quote(it.file_path)}&lib={it.library.slug}"

def index(request):
    cfg = load_config()
    pin_required = cfg.get("hidden_pin", None)

    if request.session.get("show_hidden"):
        libs = Library.objects.all()
    else:
        libs = Library.objects.filter(hidden=False)

    media_items = list(
        MediaItem.objects
        .filter(library__hidden=False, is_video=True)
        .order_by("-id")[:10]
    )

    posterize(media_items=media_items)

    all_collections = list(Collection.objects.all())
    collections_to_show = sample(all_collections, 2) if len(all_collections) >= 2 else all_collections

    collections_data = []

    for col in collections_to_show:
        movies = col.items.filter().order_by("id")
        posterize(media_items=movies)
        collections_data.append({
            "collection": col,
            "movies": movies,
        })

    return render(request, "index.html", {
        "libraries": libs,
        "pin_required": pin_required is not None,
        "show_hidden": request.session.get("show_hidden", False),
        "media_items": media_items,
        "collections": collections_data,
    })

def get_folder_size(folder):
    size = 0
    for it in folder.items.all():
        if isinstance(it, FolderItem):
            size += get_folder_size(it)
        else:
            size += it.file_size
    return size

def library_view(request, lib_slug):
    lib = get_object_or_404(Library, slug=lib_slug)
    if lib.hidden and not request.session.get("show_hidden"):
        raise Http404("Library hidden")

    # Get optional folder id for drill-down
    folder_id = request.GET.get("folder")  # None for root
    current_path = []

    folder = None

    if lib.type == "pictures":
        if folder_id:
            folder = get_object_or_404(FolderItem, id=folder_id, library=lib)
            subfolders = folder.subfolders.all().order_by("name")
            pictures = folder.items.all().order_by("title")

            f = folder
            while f:
                current_path.insert(0, f.name)
                f = f.parent
        else:
            # root-level folders and pictures
            subfolders = lib.folders.filter(parent__isnull=True).order_by("name")
            pictures = lib.items.filter(folder__isnull=True).order_by("title")

        # Combine folders and pictures, folders first
        items = list(subfolders) + list(pictures)

        # Build URLs for each item
        for it in items:
            if isinstance(it, FolderItem):
                it.viewer_url = f"?folder={it.id}"  # drill-down
                it.poster_url = f"/media/preview/?path={it.poster}" if it.poster else "/static/images/mediahub-placeholder.jpg"
            else:  # MediaItem
                if lib.hidden:
                    it.poster_url = f"/media/preview/?path={quote(it.file_path)}"
                elif it.poster:
                    it.poster_url = "/static_cache/posters/" + it.poster
                else:
                    it.poster_url = "/static/images/mediahub-placeholder.jpg"

                ext = os.path.splitext(it.file_path)[1].lower()
                if ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
                    it.viewer_url = f"/media/image/?lib={lib.slug}&id={it.id}&folder={folder.path if folder else None}"
                else:
                    it.viewer_url = f"/media/player/?path={quote(it.file_path)}&lib={lib.slug}&folder={folder.path if folder else None}"

    else:
        # Movies / other types remain as before
        items = lib.items.all().order_by("title")
        for it in items:
            if lib.hidden:
                it.poster_url = f"/media/preview/?path={quote(it.file_path)}"
            elif it.poster:
                it.poster_url = "/static_cache/posters/" + it.poster
            else:
                it.poster_url = "/static/images/mediahub-placeholder.jpg"

            ext = os.path.splitext(it.file_path)[1].lower()
            if ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
                it.viewer_url = f"/media/image/?lib={lib.slug}&id={it.id}"
            else:
                it.viewer_url = f"/media/player/?path={quote(it.file_path)}&lib={lib.slug}"

    size = 0
    for it in items:
        if isinstance(it, FolderItem):
            it.item_type = "folder"
            size += get_folder_size(it)
        else:
            it.item_type = "media"
            size += it.file_size

    current_path.insert(0, lib.name)
    breadcrumb_path = "/" + "/".join(current_path)
    parent_id = folder.parent.id if folder and folder.parent else None

    return render(request, "library.html", {
        "library": lib, 
        "size": size,
        "items": items, 
        "breadcrumb_path": breadcrumb_path, 
        "parent_id": parent_id,
        "item_count": len(items),
    })

def refresh_view(request):
    lock = scan_once_safe()
    return JsonResponse({"lock": lock})

def stream_media(request):
    path = unquote(request.GET.get("path"))

    if not path or not os.path.exists(path):
        raise Http404("File not found")

    file_size = os.path.getsize(path)
    mime_type, _ = mimetypes.guess_type(path)
    mime_type = mime_type or "application/octet-stream"

    range_header = request.headers.get("Range")
    if range_header:
        # Example: "Range: bytes=1000-"
        bytes_range = range_header.strip().split("=")[1]
        start, end = bytes_range.split("-")[0], bytes_range.split("-")[1] or None
        start = int(start) if start else 0
        end = int(end) if end else file_size - 1
        length = end - start + 1

        def file_gen(path, start, length, block_size=8192):
            with open(path, "rb") as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk_size = min(block_size, remaining)
                    data = f.read(chunk_size)
                    if not data:
                        break
                    yield data
                    remaining -= len(data)

        resp = StreamingHttpResponse(
            file_gen(path, start, length),
            status=206,
            content_type=mime_type,
        )
        resp["Content-Length"] = str(length)
        resp["Content-Range"] = f"bytes {start}-{end}/{file_size}"
        resp["Accept-Ranges"] = "bytes"
        return resp

    # If no Range header → normal full response
    resp = StreamingHttpResponse(FileWrapper(open(path, "rb")), content_type=mime_type)
    resp["Content-Length"] = str(file_size)
    resp["Accept-Ranges"] = "bytes"
    return resp

def preview_media(request):
    path = unquote(request.GET.get("path"))
    if not path or not os.path.exists(path):
        raise Http404("File not found")

    ext = os.path.splitext(path)[1].lower()
    if ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
        return FileResponse(open(path, "rb"), content_type=mimetypes.guess_type(path)[0])

    thumb_path = get_preview(path)

    if not thumb_path:
        raise Http404("Preview not available")
    else:
        return FileResponse(open(thumb_path, "rb"), content_type="image/jpeg")

def player_view(request):
    path = unquote(request.GET.get("path"))
    lib_slug = request.GET.get("lib")

    if not path or not os.path.exists(path):
        raise Http404("File not found")
    
    vid = MediaItem.objects.get(file_path=path)
    progress = PlaybackProgress.objects.filter(media_item=vid.id).first()

    if vid.library.sync:
        backdrop_url = "/static_cache/backdrop/" + vid.backdrop if vid.backdrop else vid.poster
    else:
        backdrop_url = "/static_cache/" + os.path.basename(get_preview(path))

    subtitles = get_or_fetch(vid)

    return render(request, "player.html", {
        "item": vid,
        "file_path": quote(path), 
        "backdrop_url": backdrop_url,
        "item_id": vid.id, 
        "lib_slug": lib_slug, 
        "breadcrumb_path": "/" + vid.title,
        "progress": progress.position if progress else 0,
        "subtitles": subtitles,
    })

def show_hidden(request):
    if request.method == "POST":
        code = request.POST.get("code")
        cfg = load_config()
        if code == str(cfg.get("hidden_pin", "")):
            request.session["show_hidden"] = True
    return redirect("/")

def hide_hidden(request):
    if request.method == "POST":
        request.session.pop("show_hidden", None)
    return redirect("/")

def match_score(name, query):
    """
    Higher score if query matches more of the start of `name`.
    Full prefix match gives highest score.
    """
    name_lower = name.lower()
    query_lower = query.lower()
    
    if name_lower.startswith(query_lower):
        # exact prefix match: longer query → higher score
        return len(query_lower) / len(name_lower)
    elif query_lower in name_lower:
        # partial match inside string: smaller score
        return 0.5 * len(query_lower) / len(name_lower)
    else:
        return 0


def search_view(request):
    query = request.GET.get("q", "").strip()
    show_hidden = request.session.get("show_hidden", False)
    results = []

    if query:
        # Search in movies / pictures / folders
        media_qs = MediaItem.objects.filter(
            Q(title__icontains=query)
        )
        folder_qs = FolderItem.objects.filter(
            Q(name__icontains=query)
        )

        # If hidden is disabled, exclude hidden libraries
        if not show_hidden:
            media_qs = media_qs.exclude(library__hidden=True)
            folder_qs = folder_qs.exclude(library__hidden=True)

        results = [(obj, match_score(getattr(obj, 'title', getattr(obj, 'name', '')), query)) for obj in list(media_qs) + list(folder_qs)]

        results.sort(key=lambda x: x[1], reverse=True)

        # Limit to 5 overall
        results = [obj for obj, _ in results][:5]

        final_results = []
        # Combine results
        for item in results:
            if hasattr(item, 'ext'):
                final_results.append({
                    "type": "media",
                    "title": item.title,
                    "id": item.id,
                    "lib_slug": item.library.slug,
                    "file_path": item.file_path,
                    "isvideo": item.is_video,
                    "folder": item.folder.path if item.folder else None
                })
            else:
                final_results.append({
                    "type": "folder",
                    "title": item.name,
                    "id": item.id,
                    "lib_slug": item.library.slug
                })


    return JsonResponse(final_results, safe=False)

def set_poster(request, item_id):
    try:
        item = MediaItem.objects.get(id=item_id)
        if item.library.sync or not item.is_video:
            return JsonResponse({"success": False, "error": "Poster editing not allowed"})

        data = json.loads(request.body)
        seconds = int(data.get("time", 5))
        
        thumb_path = settings.CACHE_DIR / f"preview_{os.path.basename(item.file_path)}.jpg"

        subprocess.run([
            "ffmpeg", "-y",
            "-ss", str(seconds),
            "-i", item.file_path,
            "-vframes", "1", "-q:v", "2",
            str(thumb_path)
        ], check=True)

        return JsonResponse({"success": True})
    except MediaItem.DoesNotExist:
        return JsonResponse({"success": False, "error": "Item not found"})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})
    
def save_progress(request, item_id):
    data = json.loads(request.body)
    time = int(data.get("time", 0))
    item = MediaItem.objects.get(id=item_id)

    progress, _ = PlaybackProgress.objects.update_or_create(
        media_item=item,
        defaults={"position": time}
    )
    return JsonResponse({"success": True})