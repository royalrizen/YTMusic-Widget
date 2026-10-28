import base64
import json
import os
import re
import requests
from pathlib import Path
from html import escape, unescape

BASE_URL = "https://music.youtube.com"
SCRIPT_DIR = Path(__file__).resolve().parent

COOKIE_JSON = os.environ.get("YTMUSIC_COOKIES")
OUTPUT_FILE = SCRIPT_DIR / "now_playing.json"
SVG_FILE = SCRIPT_DIR / "listening.svg"

SHOW_ALL_SONGS = False
MAX_SONGS = 50


def create_session():
    if not COOKIE_JSON:
        raise RuntimeError("YTMUSIC_COOKIES secret is missing.")

    try:
        cookies = json.loads(COOKIE_JSON)
    except json.JSONDecodeError as exc:
        raise RuntimeError("YTMUSIC_COOKIES must contain valid JSON.") from exc

    if not isinstance(cookies, dict):
        raise ValueError("YTMUSIC_COOKIES must contain a JSON object.")

    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/139.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    })

    for name, value in cookies.items():
        session.cookies.set(
            name,
            str(value),
            domain=".youtube.com",
            path="/",
        )

    return session


def fetch_history(session):
    response = session.get(
        f"{BASE_URL}/history",
        headers={
            "Referer": BASE_URL + "/",
            "Cache-Control": "no-cache, no-store, max-age=0",
            "Pragma": "no-cache",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.text


def extract_initial_data(html):
    pattern = r"""initialData\.push\(\{[^}]*data:\s*'((?:\\.|[^'])*)'"""

    for match in re.findall(pattern, html):
        decoded = re.sub(
            r"\\x([0-9a-fA-F]{2})",
            lambda m: chr(int(m.group(1), 16)),
            match,
        )

        try:
            data = json.loads(decoded)
            if isinstance(data, dict) and contains_history(data):
                return data
        except json.JSONDecodeError:
            continue

    return None


def contains_history(data):
    text = json.dumps(data, ensure_ascii=False)
    return "musicShelfRenderer" in text or "FEmusic_history" in text


def get_runs(column):
    return (
        column.get("musicResponsiveListItemFlexColumnRenderer", {})
        .get("text", {})
        .get("runs", [])
    )


def parse_track(renderer):
    title = None
    artist = None
    video_id = None
    fallback_artists = []

    thumbnails = (
        renderer.get("thumbnail", {})
        .get("musicThumbnailRenderer", {})
        .get("thumbnail", {})
        .get("thumbnails", [])
    )

    thumbnail_url = max(
        thumbnails,
        key=lambda t: t.get("width", 0) * t.get("height", 0),
        default={},
    ).get("url")

    for column in renderer.get("flexColumns", []):
        for run in get_runs(column):
            text = run.get("text", "").strip()
            if not text:
                continue

            endpoint = run.get("navigationEndpoint", {})
            watch = endpoint.get("watchEndpoint", {})

            if watch and not title:
                title = text
                video_id = watch.get("videoId")
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

    if not title or not artist:
        return None

    return {
        "title": unescape(title),
        "artist": unescape(artist),
        "url": (
            f"https://music.youtube.com/watch?v={video_id}"
            if video_id
            else None
        ),
        "thumbnail": thumbnail_url,
    }


def get_songs(data, all_songs=False, limit=50):
    songs = []
    seen = set()

    tabs = (
        data.get("contents", {})
        .get("singleColumnBrowseResultsRenderer", {})
        .get("tabs", [])
    )

    for tab in tabs:
        sections = (
            tab.get("tabRenderer", {})
            .get("content", {})
            .get("sectionListRenderer", {})
            .get("contents", [])
        )

        for section in sections:
            shelf = section.get("musicShelfRenderer")
            if not shelf:
                continue

            for item in shelf.get("contents", []):
                renderer = item.get("musicResponsiveListItemRenderer")
                if not renderer:
                    continue

                song = parse_track(renderer)
                if not song:
                    continue

                video_id = (
                    song["url"].split("v=", 1)[1]
                    if song["url"]
                    else None
                )

                if video_id:
                    if video_id in seen:
                        continue
                    seen.add(video_id)

                songs.append(song)

                if not all_songs or len(songs) >= limit:
                    return songs

    return songs


def embed_thumbnail(thumbnail_url):
    if not thumbnail_url:
        return None

    try:
        response = requests.get(
            thumbnail_url,
            timeout=15,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 Chrome/139.0.0.0 "
                    "Safari/537.36"
                )
            },
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
            print(f"Unexpected thumbnail content type: {content_type}")
            return None

        encoded = base64.b64encode(response.content).decode("ascii")
        return f"data:{content_type};base64,{encoded}"

    except requests.RequestException as exc:
        print(f"Could not download thumbnail: {exc}")
        return None


def create_svg(song):
    title = escape(song["title"])
    artist = escape(song["artist"])
    url = escape(song.get("url") or BASE_URL, quote=True)
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

      <text x="150" y="34"
            fill="#FFFFFF"
            font-family="Arial,sans-serif"
            font-size="10"
            font-weight="bold"
            letter-spacing="1.8">NOW PLAYING</text>

      <a href="{url}">
        <text x="150" y="66"
              fill="#FFFFFF"
              font-family="Arial,sans-serif"
              font-size="17"
              font-weight="bold">{title[:34]}</text>
      </a>

      <text x="150" y="91"
            fill="#FFFFFF"
            opacity="0.85"
            font-family="Arial,sans-serif"
            font-size="13">{artist[:36]}</text>

      <text x="150" y="121"
            fill="#FFFFFF"
            opacity="0.7"
            font-family="Arial,sans-serif"
            font-size="10"
            letter-spacing="1.5">YOUTUBE MUSIC</text>

      <g transform="translate(380,105)" fill="#FFFFFF" opacity="0.9">
        <rect x="0" y="10" width="4" height="12" rx="2"/>
        <rect x="8" y="3" width="4" height="19" rx="2"/>
        <rect x="16" y="0" width="4" height="22" rx="2"/>
        <rect x="24" y="7" width="4" height="15" rx="2"/>
      </g>

    </svg>"""


def create_history_svg(songs):
    if not songs:
        raise RuntimeError("No songs found in listening history.")

    card_height = 152
    gap = 10
    total_height = len(songs) * card_height + (len(songs) - 1) * gap

    cards = []

    for index, song in enumerate(songs):
        svg = create_svg(song)
        inner = svg[svg.index("<defs>"):svg.rindex("</svg>")]
        y = index * (card_height + gap)

        cards.append(
            f'<svg x="0" y="{y}" width="440" height="{card_height}" '
            f'viewBox="0 0 440 152">{inner}</svg>'
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg"
        width="440" height="{total_height}"
        viewBox="0 0 440 {total_height}">
        {''.join(cards)}
    </svg>"""


def main():
    with create_session() as session:
        html = fetch_history(session)

    data = extract_initial_data(html)
    if not data:
        raise RuntimeError("Could not extract YouTube Music history.")

    songs = get_songs(
        data,
        all_songs=SHOW_ALL_SONGS,
        limit=MAX_SONGS,
    )

    if not songs:
        raise RuntimeError("No songs found in listening history.")

    output = songs if SHOW_ALL_SONGS else songs[0]

    OUTPUT_FILE.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    svg = (
        create_history_svg(songs)
        if SHOW_ALL_SONGS
        else create_svg(songs[0])
    )

    SVG_FILE.write_text(svg, encoding="utf-8")

    print(f"Saved {len(songs)} song(s).")
    print(f"JSON: {OUTPUT_FILE}")
    print(f"SVG:  {SVG_FILE}")


if __name__ == "__main__":
    try:
        main()
    except (
        OSError,
        json.JSONDecodeError,
        requests.RequestException,
        RuntimeError,
    ) as exc:
        print(f"Error: {exc}")
