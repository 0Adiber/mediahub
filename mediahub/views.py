from django.shortcuts import render, redirect, get_object_or_404
from django.http import StreamingHttpResponse, Http404, FileResponse
from .models import Library, MediaItem
from .scanner import scan_once, load_config
import os, mimetypes, subprocess
from wsgiref.util import FileWrapper
from django.conf import settings
from PIL import Image


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
    items = lib.items.all().order_by("title")

    # build URLs depending on type
    for idx, it in enumerate(items):
        if lib.hidden:
            it.poster_url = f"/media/preview/?path={it.file_path}"
        elif it.poster:
            it.poster_url = "/static_cache/posters/" + it.poster
        else:
            it.poster_url = "/static/mediahub-placeholder.png"

        ext = os.path.splitext(it.file_path)[1].lower()
        if ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
            it.viewer_url = f"/media/image/?lib={lib.slug}&index={idx}"
        else:
            it.viewer_url = f"/media/player/?path={it.file_path}&lib={lib.slug}"
    return render(request, "library.html", {"library": lib, "items": items})

def refresh_view(request):
    scan_once()
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
    if not path or not os.path.exists(path):
        raise Http404("File not found")
    return render(request, "player.html", {"file_path": path, "lib_slug": lib_slug})

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
    index = int(request.GET.get("index", 0))

    lib = get_object_or_404(Library, slug=lib_slug)
    items = list(lib.items.filter(
        file_path__iregex=r"\.(jpg|jpeg|png|gif|webp)$"
    ).order_by("title"))

    if index < 0 or index >= len(items):
        raise Http404("Image not found")

    current = items[index]
    prev_index = index - 1 if index > 0 else None
    next_index = index + 1 if index < len(items) - 1 else None

    return render(request, "image_viewer.html", {
        "library": lib,
        "current": current,
        "prev_index": prev_index,
        "next_index": next_index,
    })
