import requests
import zipfile
import os
import io
import re
from django.conf import settings

def search_subtitles_by_tmdb(tmdb_id: int, languages: str):
    """Search for subtitles via SubDL API given a TMDB ID, filtering by languages."""
    url = "https://api.subdl.com/api/v1/subtitles"

    if not settings.SUBDL_API_KEY:
        return []

    params = {
        "api_key": settings.SUBDL_API_KEY,
        "tmdb_id": tmdb_id,
        "languages": languages,
        "type": "movie",
    }
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    data = resp.json()

    return data.get("subtitles", [])

def download_subdl_subtitle(sub_info: dict, path: str):
    """
    Download a subtitle ZIP from SubDL, extract the first .srt,
    convert it to .vtt, and save to the given final file path.
    
    Args:
        sub_info: One item from SubDL "subtitles" list (contains 'url').
        path: Full path to the final .vtt file (e.g., /some/dir/subtitle.vtt).
    """
    # Build download link
    dl_link = sub_info.get("url")
    dl_link = f"https://dl.subdl.com{dl_link}"

    # Download ZIP
    resp = requests.get(dl_link)
    resp.raise_for_status()


    try: # BadZipFile at /media/player/
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            # Find .srt files inside the archive
            srt_files = [f for f in zf.namelist() if f.lower().endswith(".srt")]
            if not srt_files:
                return

            chosen_file = srt_files[0]

            # Read .srt content
            with zf.open(chosen_file) as src:
                srt_text = src.read().decode("utf-8", errors="ignore")

            # Convert to .vtt
            vtt_text = "WEBVTT\n\n" + srt_text.replace(",", ".")

            # Save as .vtt
            with open(path, "w", encoding="utf-8") as dst:
                dst.write(vtt_text)
    except:
        return

def fetch_subtitles(tmdb_id: int):
    """Main: fetch English subtitle via SubDL, store it under SUBTITLES_DIR/tmdb_id/."""
    languages = "EN" # comma separated list
    subs = search_subtitles_by_tmdb(tmdb_id, languages)
    if not subs:
        print(f"No subtitles found for tmdb_id={tmdb_id}")
        return {}

    for sub in subs:
        lang = sub.get("language")
        movie_folder = os.path.join(settings.SUBTITLES_DIR, str(tmdb_id), lang)
        os.makedirs(movie_folder, exist_ok=True)

        next_num = get_next_subtitle_num(movie_folder, lang)

        fname = sub.get("file_name", f"{lang}-{next_num}.vtt")
        path = os.path.join(movie_folder, fname)
        download_subdl_subtitle(sub, path)

    return get_subtitles(tmdb_id)

def get_next_subtitle_num(directory: str, lang: str, ext: str = ".vtt") -> int:
    """
    Scan a directory for files matching prefixNN.ext (e.g., file-01.txt),
    find the highest NN, and return the path for the next number.
    """
    pattern = re.compile(rf"^{re.escape(lang)}-(\d+){re.escape(ext)}$")
    max_num = 0

    for fname in os.listdir(directory):
        match = pattern.match(fname)
        if match:
            num = int(match.group(1))
            max_num = max(max_num, num)

    return max_num + 1

def get_subtitles(tmdb_id: int):
    directory = os.path.join(settings.SUBTITLES_DIR, str(tmdb_id))

    if not os.path.exists(directory):
        return {}

    subtitles = {}
    for item in os.listdir(directory):
        lang_dir = os.path.join(directory, item)
        if os.path.isdir(lang_dir):
            subtitles[item] = []
            for sub in os.listdir(lang_dir):
                subtitles[item].append(sub)

    return subtitles

def srt_to_vtt(srt_path: str, vtt_path: str):
    with open(srt_path, "r", encoding="utf-8") as srt_file:
        srt_content = srt_file.read()

    # Replace commas with dots in timecodes
    vtt_content = "WEBVTT\n\n" + srt_content.replace(",", ".")

    with open(vtt_path, "w", encoding="utf-8") as vtt_file:
        vtt_file.write(vtt_content)

def get_or_fetch_subtitles(tmdb_id):
    subtitles = get_subtitles(tmdb_id)
    if len(subtitles) == 0:
        subtitles = fetch_subtitles(tmdb_id)
    return subtitles