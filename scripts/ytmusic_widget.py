import os
import re
import json
import html
import base64
import codecs
from pathlib import Path
import requests
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
load_dotenv(PROJECT_DIR / ".env")
BASE_URL = "https://music.youtube.com"
COOKIE_JSON = os.environ.get("YTMUSIC_COOKIES")
JSON_OUTPUT = PROJECT_DIR / "now_playing.json"
SVG_OUTPUT = PROJECT_DIR / "listening.svg"


def create_session():
    if not COOKIE_JSON:
        raise RuntimeError("Configuration error.")

    try:
        cookies = json.loads(COOKIE_JSON)
    except (ValueError, TypeError):
        raise RuntimeError("Configuration error.") from None

    if not isinstance(cookies, (dict, list)):
        raise RuntimeError("Configuration error.")

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    })

    if isinstance(cookies, dict):
        for name, value in cookies.items():
            session.cookies.set(name, str(value), domain=".youtube.com")
    else:
        for cookie in cookies:
            if isinstance(cookie, dict) and "name" in cookie and "value" in cookie:
                session.cookies.set(
                    cookie["name"],
                    str(cookie["value"]),
                    domain=cookie.get("domain", ".youtube.com"),
                    path=cookie.get("path", "/"),
                )

    return session


def fetch_history(session):
    response = session.get(f"{BASE_URL}/history", timeout=30)
    response.raise_for_status()
    return response.text


def contains_history(data):
    if isinstance(data, dict):
        if "musicShelfRenderer" in data:
            return True
        return any(contains_history(value) for value in data.values())

    if isinstance(data, list):
        return any(contains_history(item) for item in data)

    return False


def extract_initial_data(page):
    pattern = (
        r"initialData\.push\(\{path:\s*'([^']*)'.*?"
        r"data:\s*'((?:\\.|[^'])*)'\s*\}\);"
    )

    for match in re.finditer(pattern, page, re.DOTALL):
        path = match.group(1)
        raw_data = match.group(2)
        decoded = raw_data.replace(r"\/", "/")

        try:
            decoded = codecs.decode(decoded, "unicode_escape")
            data = json.loads(decoded)
        except (ValueError, UnicodeError):
            continue

        if "browse" in path and contains_history(data):
            return data

    return None


def get_text(value):
    if not isinstance(value, dict):
        return ""

    if "simpleText" in value:
        return value["simpleText"]

    return "".join(
        run.get("text", "")
        for run in value.get("runs", [])
        if isinstance(run, dict)
    )


def find_shelves(data):
    shelves = []

    if isinstance(data, dict):
        shelf = data.get("musicShelfRenderer")

        if isinstance(shelf, dict):
            shelves.append(shelf)

        for value in data.values():
            shelves.extend(find_shelves(value))

    elif isinstance(data, list):
        for item in data:
            shelves.extend(find_shelves(item))

    return shelves


def get_video_id(renderer):
    video_id = renderer.get("playlistItemData", {}).get("videoId")

    if video_id:
        return video_id

    watch = renderer.get("navigationEndpoint", {}).get("watchEndpoint", {})

    if watch.get("videoId"):
        return watch["videoId"]

    for column in renderer.get("flexColumns", []):
        column_renderer = column.get(
            "musicResponsiveListItemFlexColumnRenderer", {}
        )

        for run in column_renderer.get("text", {}).get("runs", []):
            watch = (
                run.get("navigationEndpoint", {})
                .get("watchEndpoint", {})
            )

            if watch.get("videoId"):
                return watch["videoId"]

    return ""


def get_thumbnail(renderer):
    thumbnails = []

    for key in ("thumbnail", "thumbnailRenderer"):
        value = renderer.get(key, {})

        thumbnails.extend(
            value.get("musicThumbnailRenderer", {})
            .get("thumbnail", {})
            .get("thumbnails", [])
        )

        thumbnails.extend(
            value.get("croppedSquareThumbnailRenderer", {})
            .get("thumbnail", {})
            .get("thumbnails", [])
        )

    return max(
        thumbnails,
        key=lambda item: item.get("width", 0) * item.get("height", 0),
        default={},
    ).get("url", "")


def parse_track(renderer):
    title = ""
    artist = ""
    fallback_artists = []
    columns = renderer.get("flexColumns", [])

    for column in columns:
        column_renderer = column.get(
            "musicResponsiveListItemFlexColumnRenderer", {}
        )

        for run in column_renderer.get("text", {}).get("runs", []):
            text = run.get("text", "").strip()

            if not text:
                continue

            endpoint = run.get("navigationEndpoint", {})
            watch = endpoint.get("watchEndpoint", {})

            if watch.get("videoId") and not title:
                title = text
                continue

            browse = endpoint.get("browseEndpoint", {})
            config = (
                browse.get(
                    "browseEndpointContextSupportedConfigs", {}
                )
                .get("browseEndpointContextMusicConfig", {})
            )

            if config.get("pageType") == "MUSIC_PAGE_TYPE_ARTIST":
                if not artist:
                    artist = text
            elif text != title:
                fallback_artists.append(text)

    if not artist and fallback_artists:
        artist = fallback_artists[0]

    if not title:
        texts = []

        for column in columns:
            column_renderer = column.get(
                "musicResponsiveListItemFlexColumnRenderer", {}
            )
            text = get_text(column_renderer.get("text", {}))

            if text:
                texts.append(text)

        if texts:
            title = texts[0]

        if not artist and len(texts) > 1:
            artist = texts[1]

    if not title:
        return None

    video_id = get_video_id(renderer)

    return {
        "title": html.unescape(title),
        "artist": html.unescape(artist or "Unknown artist"),
        "album": "",
        "videoId": video_id,
        "url": (
            f"https://music.youtube.com/watch?v={video_id}"
            if video_id
            else ""
        ),
        "thumbnail": get_thumbnail(renderer),
    }


def extract_tracks(data):
    tracks = []
    seen = set()

    for shelf in find_shelves(data):
        for item in shelf.get("contents", []):
            renderer = item.get("musicResponsiveListItemRenderer")

            if not isinstance(renderer, dict):
                continue

            track = parse_track(renderer)

            if not track:
                continue

            identifier = track["videoId"] or (
                track["title"] + track["artist"]
            )

            if identifier in seen:
                continue

            seen.add(identifier)
            tracks.append(track)

    return tracks


def embed_thumbnail(thumbnail_url):
    if not thumbnail_url:
        return None

    try:
        response = requests.get(
            thumbnail_url,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()

        content_type = response.headers.get(
            "Content-Type", "image/jpeg"
        ).split(";")[0].strip().lower()

        if content_type not in (
            "image/jpeg",
            "image/png",
            "image/webp",
            "image/gif",
        ):
            return None

        encoded = base64.b64encode(response.content).decode("ascii")
        return f"data:{content_type};base64,{encoded}"

    except requests.RequestException:
        return None


def create_svg(song):
    title = html.escape(song["title"])
    artist = html.escape(song["artist"])
    url = html.escape(song.get("url") or BASE_URL, quote=True)
    thumbnail = embed_thumbnail(song.get("thumbnail"))

    if thumbnail:
        image = f"""
        <image href="{thumbnail}"
               x="24" y="24" width="104" height="104"
               preserveAspectRatio="xMidYMid slice"
               clip-path="url(#coverClip)"/>
        """
    else:
        image = """
        <rect x="24" y="24" width="104" height="104" rx="8"
              fill="#182169"/>
        <text x="76" y="86" text-anchor="middle"
              font-size="34" fill="#FFFFFF">♫</text>
        """

    return f"""<svg xmlns="http://www.w3.org/2000/svg"
        width="440" height="152" viewBox="0 0 440 152">
      <defs>
        <clipPath id="coverClip">
          <rect x="24" y="24" width="104" height="104" rx="4"/>
        </clipPath>
        <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="#182169"/>
          <stop offset="100%" stop-color="#182169"/>
        </linearGradient>
      </defs>
      <rect width="440" height="152" rx="14" fill="url(#bg)"/>
      {image}
      <text x="150" y="34" fill="#FFFFFF"
            font-family="Arial,sans-serif" font-size="10"
            font-weight="bold" letter-spacing="1.8">NOW PLAYING</text>
      <a href="{url}">
        <text x="150" y="66" fill="#FFFFFF"
              font-family="Arial,sans-serif" font-size="17"
              font-weight="bold">{title[:34]}</text>
      </a>
      <text x="150" y="91" fill="#FFFFFF" opacity="0.85"
            font-family="Arial,sans-serif" font-size="13">{artist[:36]}</text>
      <text x="150" y="121" fill="#FFFFFF" opacity="0.7"
            font-family="Arial,sans-serif" font-size="10"
            letter-spacing="1.5">YOUTUBE MUSIC</text>
      <g transform="translate(380,105)" fill="#FFFFFF" opacity="0.9">
        <rect x="0" y="10" width="4" height="12" rx="2"/>
        <rect x="8" y="3" width="4" height="19" rx="2"/>
        <rect x="16" y="0" width="4" height="22" rx="2"/>
        <rect x="24" y="7" width="4" height="15" rx="2"/>
      </g>
    </svg>"""


def main():
    JSON_OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    with create_session() as session:
        page = fetch_history(session)

    data = extract_initial_data(page)

    if data is None:
        raise RuntimeError("Could not retrieve music data.")

    tracks = extract_tracks(data)

    if not tracks:
        raise RuntimeError("No music data available.")

    song = tracks[0]

    JSON_OUTPUT.write_text(
        json.dumps(song, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    SVG_OUTPUT.write_text(create_svg(song), encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, requests.RequestException, RuntimeError):
        print("Unable to update the Now Playing card.")
