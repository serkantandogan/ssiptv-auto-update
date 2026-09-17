from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

import requests
import yaml


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "sources.yml"
PUBLIC_DIR = ROOT / "public"
PLAYLIST_PATH = PUBLIC_DIR / "ssiptv.m3u"
REPORT_PATH = PUBLIC_DIR / "validation-report.json"


EXTINF_RE = re.compile(r'#EXTINF:(?P<duration>-?\d+)(?P<attrs>[^,]*),(?P<name>.*)')
ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')


@dataclass(frozen=True)
class Channel:
    name: str
    url: str
    category: str
    attrs: dict[str, str]


def load_config() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def read_source(source: dict) -> str:
    if source.get("url"):
        response = requests.get(source["url"], timeout=20)
        response.raise_for_status()
        return response.text

    if source.get("file"):
        path = ROOT / source["file"]
        return path.read_text(encoding="utf-8")

    raise ValueError(f"Source {source.get('name', '<unnamed>')} has no url or file")


def parse_attrs(raw_attrs: str) -> dict[str, str]:
    return {key: value for key, value in ATTR_RE.findall(raw_attrs)}


def infer_category(name: str, attrs: dict[str, str], fallback: str, rules: dict) -> str:
    group = attrs.get("group-title", "").strip()
    if group:
        return group

    lowered = name.lower()
    for category, keywords in rules.items():
        if any(str(keyword).lower() in lowered for keyword in keywords):
            return category

    return fallback or "Other"


def parse_m3u(text: str, fallback_category: str, rules: dict) -> Iterable[Channel]:
    pending: tuple[str, dict[str, str]] | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("#EXTINF:"):
            match = EXTINF_RE.match(line)
            if not match:
                pending = None
                continue
            attrs = parse_attrs(match.group("attrs"))
            name = match.group("name").strip() or attrs.get("tvg-name", "").strip()
            pending = (name, attrs)
            continue

        if line.startswith("#"):
            continue

        if pending and is_probable_stream_url(line):
            name, attrs = pending
            category = infer_category(name, attrs, fallback_category, rules)
            yield Channel(name=name, url=line, category=category, attrs=attrs)
        pending = None


def is_probable_stream_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def validate_stream(url: str, timeout: int, user_agent: str, verify_tls: bool) -> tuple[bool, str]:
    headers = {"User-Agent": user_agent}

    for method in ("HEAD", "GET"):
        try:
            response = requests.request(
                method,
                url,
                headers=headers,
                timeout=timeout,
                stream=True,
                allow_redirects=True,
                verify=verify_tls,
            )
            if response.status_code < 400:
                return True, f"{method} {response.status_code}"
            last_status = f"{method} {response.status_code}"
        except requests.RequestException as exc:
            last_status = f"{method} {exc.__class__.__name__}"

    return False, last_status


def channel_key(channel: Channel) -> tuple[str, str]:
    return (channel.name.strip().lower(), channel.url.strip())


def format_extinf(channel: Channel) -> str:
    attrs = dict(channel.attrs)
    attrs["group-title"] = channel.category
    attrs.setdefault("tvg-name", channel.name)
    attr_text = " ".join(f'{key}="{value}"' for key, value in sorted(attrs.items()))
    return f"#EXTINF:-1 {attr_text},{channel.name}"


def write_playlist(channels: list[Channel]) -> None:
    PUBLIC_DIR.mkdir(exist_ok=True)
    ordered = sorted(channels, key=lambda item: (item.category.lower(), item.name.lower()))

    lines = ["#EXTM3U"]
    for channel in ordered:
        lines.append(format_extinf(channel))
        lines.append(channel.url)

    PLAYLIST_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    config = load_config()
    rules = config.get("category_rules") or {}
    validation = config.get("validation") or {}
    timeout = int(validation.get("timeout_seconds", 8))
    user_agent = validation.get("user_agent", "SSIPTV-Auto-Update/1.0")
    verify_tls = bool(validation.get("verify_tls", True))

    seen: set[tuple[str, str]] = set()
    valid_channels: list[Channel] = []
    report: list[dict] = []

    for source in config.get("sources", []):
        if not source.get("enabled", True):
            continue

        source_name = source.get("name", "Unnamed source")
        fallback_category = source.get("category", "Other")

        try:
            text = read_source(source)
            channels = list(parse_m3u(text, fallback_category, rules))
        except Exception as exc:
            report.append({"source": source_name, "ok": False, "error": str(exc)})
            continue

        for channel in channels:
            key = channel_key(channel)
            if key in seen:
                continue
            seen.add(key)

            ok, status = validate_stream(channel.url, timeout, user_agent, verify_tls)
            report.append(
                {
                    "source": source_name,
                    "channel": channel.name,
                    "category": channel.category,
                    "url": channel.url,
                    "ok": ok,
                    "status": status,
                }
            )
            if ok:
                valid_channels.append(channel)

    write_playlist(valid_channels)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(valid_channels)} valid channels to {PLAYLIST_PATH}")


if __name__ == "__main__":
    main()

