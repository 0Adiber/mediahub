from django.shortcuts import render, redirect, get_object_or_404
from django.http import StreamingHttpResponse, Http404, FileResponse, JsonResponse
from .models import Library, MediaItem, FolderItem
from .scanner import scan_once_safe, load_config
import os, mimetypes, subprocess
from wsgiref.util import FileWrapper
from django.conf import settings
from django.db.models import Q
from PIL import Image
import threading

def index(request):
    cfg = load_config()
    pin_required = cfg.get("hidden_pin", None)

    if request.session.get("show_hidden"):
        libs = Library.objects.all()
    else:
        libs = Library.objects.filter(hidden=False)

    return render(request, "index.html", {
        "libraries": libs,
        "pin_required": pin_required is not None,
        "show_hidden": request.session.get("show_hidden", False),
    })

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
                    it.poster_url = f"/media/preview/?path={it.file_path}"
                elif it.poster:
                    it.poster_url = "/static_cache/posters/" + it.poster
                else:
                    it.poster_url = "/static/images/mediahub-placeholder.jpg"

                ext = os.path.splitext(it.file_path)[1].lower()
                if ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
                    it.viewer_url = f"/media/image/?lib={lib.slug}&id={it.id}&folder={folder.path if folder else None}"
                else:
                    it.viewer_url = f"/media/player/?path={it.file_path}&lib={lib.slug}&folder={folder.path if folder else None}"

    else:
        # Movies / other types remain as before
        items = lib.items.all().order_by("title")
        for it in items:
            if lib.hidden:
                it.poster_url = f"/media/preview/?path={it.file_path}"
            elif it.poster:
                it.poster_url = "/static_cache/posters/" + it.poster
            else:
                it.poster_url = "/static/images/mediahub-placeholder.jpg"

            ext = os.path.splitext(it.file_path)[1].lower()
            if ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
                it.viewer_url = f"/media/image/?lib={lib.slug}&id={it.id}"
            else:
                it.viewer_url = f"/media/player/?path={it.file_path}&lib={lib.slug}"

    for it in items:
        if isinstance(it, FolderItem):
            it.item_type = "folder"
        else:
            it.item_type = "media"

    current_path.insert(0, lib.name)
    breadcrumb_path = "/" + "/".join(current_path)
    parent_id = folder.parent.id if folder and folder.parent else None

    return render(request, "library.html", {"library": lib, "items": items, "breadcrumb_path": breadcrumb_path, "parent_id": parent_id})

def refresh_view(request):
    threading.Thread(target=scan_once_safe, daemon=True).start()
    return redirect("/")

def stream_media(request):
    path = request.GET.get("path")
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
    path = request.GET.get("path")
    if not path or not os.path.exists(path):
        raise Http404("File not found")

    ext = os.path.splitext(path)[1].lower()
    if ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
        return FileResponse(open(path, "rb"), content_type=mimetypes.guess_type(path)[0])

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
            raise Http404("Preview not available")
    return FileResponse(open(thumb_path, "rb"), content_type="image/jpeg")

def player_view(request):
    path = request.GET.get("path")
    lib_slug = request.GET.get("lib")

    vid = MediaItem.objects.get(file_path=path)

    if not path or not os.path.exists(path):
        raise Http404("File not found")
    return render(request, "player.html", {"file_path": path, "lib_slug": lib_slug, "breadcrumb_path": "/" + vid.title })

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

def image_viewer(request):
    lib_slug = request.GET.get("lib")
    id = int(request.GET.get("id", 0))
    folder_path = request.GET.get("folder")

    lib = get_object_or_404(Library, slug=lib_slug)
    folder = FolderItem.objects.filter(path=folder_path).first()

    if folder:
        items = list(folder.items.all().order_by("title"))
    else:
        items = lib.items.filter(folder__isnull=True).order_by("title")

    current_index = next((i for i, it in enumerate(items) if it.id == id), None)
    prev_item = items[current_index - 1] if current_index > 0 else None
    next_item = items[current_index + 1] if current_index < len(items) - 1 else None

    current = MediaItem.objects.get(id=id)

    parent_id = folder.id if folder else None

    current_path = []
    
    while folder:
        current_path.insert(0, folder.name)
        folder = folder.parent

    current_path.insert(0, lib.name)
    current_path.append(str(current.title))
    breadcrumb_path = "/" + "/".join(current_path)

    return render(request, "image_viewer.html", {
        "library": lib,
        "current": current,
        "parent_id": parent_id,
        "breadcrumb_path": breadcrumb_path,
        "folder": folder_path,
        "next_item": next_item,
        "prev_item": prev_item
    })


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

        # Limit top 5 results
        media_qs = media_qs[:5]
        folder_qs = folder_qs[:5]

        # Combine results
        for item in media_qs:
            results.append({
                "type": "media",
                "title": item.title,
                "id": item.id,
                "lib_slug": item.library.slug,
                "file_path": item.file_path,
                "isvideo": item.is_video,
                "folder": item.folder.path if item.folder else None
            })
        for folder in folder_qs:
            results.append({
                "type": "folder",
                "title": folder.name,
                "id": folder.id,
                "lib_slug": folder.library.slug,
            })

        # Limit to 5 overall
        results = results[:5]

    return JsonResponse(results, safe=False)
