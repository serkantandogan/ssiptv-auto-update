from __future__ import annotations

import json
import re
import unicodedata
from html import unescape
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def load_dynamic_channel(channel_config: dict) -> Channel:
    page_url = channel_config["page_url"]
    pattern = channel_config["url_pattern"]
    response = requests.get(page_url, timeout=20)
    response.raise_for_status()

    match = re.search(pattern, response.text)
    if not match:
        raise ValueError(f"No stream URL matched for {channel_config.get('name', page_url)}")

    stream_url = unescape(match.group(1)).replace("\\/", "/")
    if not is_probable_stream_url(stream_url):
        raise ValueError(f"Matched URL is not a stream URL: {stream_url}")

    attrs = dict(channel_config.get("attrs") or {})
    attrs.setdefault("tvg-name", channel_config["name"])
    return Channel(
        name=channel_config["name"],
        url=stream_url,
        category=channel_config.get("category", "Other"),
        attrs=attrs,
    )


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


def normalize_text(value: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", ascii_text.lower()).strip()


def matches_selected_channel(channel: Channel, wanted: dict) -> bool:
    haystack = normalize_text(" ".join([channel.name, *channel.attrs.values()]))
    patterns = wanted.get("match") or [wanted.get("name", "")]
    if isinstance(patterns, str):
        patterns = [patterns]
    return any(normalize_text(pattern) in haystack for pattern in patterns)


def apply_selected_channels(
    candidates: list[tuple[str, Channel]],
    selected_channels: list[dict],
    report: list[dict],
) -> list[tuple[str, Channel]]:
    if not selected_channels:
        return candidates

    selected: list[tuple[str, Channel]] = []
    used_keys: set[tuple[str, str]] = set()

    for index, wanted in enumerate(selected_channels, start=1):
        found: tuple[str, Channel] | None = None
        for source_name, channel in candidates:
            key = channel_key(channel)
            if key in used_keys:
                continue
            if matches_selected_channel(channel, wanted):
                found = (source_name, channel)
                break

        if not found:
            report.append(
                {
                    "source": "selected_channels",
                    "channel": wanted.get("name", "<unnamed>"),
                    "category": wanted.get("category", "Other"),
                    "url": None,
                    "ok": False,
                    "status": "not found in enabled sources",
                }
            )
            continue

        source_name, channel = found
        used_keys.add(channel_key(channel))
        attrs = dict(channel.attrs)
        attrs["tvg-chno"] = str(index)
        selected.append(
            (
                source_name,
                Channel(
                    name=wanted.get("name") or channel.name,
                    url=channel.url,
                    category=wanted.get("category") or channel.category,
                    attrs=attrs,
                ),
            )
        )

    return selected


def format_extinf(channel: Channel) -> str:
    attrs = dict(channel.attrs)
    attrs["group-title"] = channel.category
    attrs.setdefault("tvg-name", channel.name)
    attr_text = " ".join(f'{key}="{value}"' for key, value in sorted(attrs.items()))
    return f"#EXTINF:-1 {attr_text},{channel.name}"


def write_playlist(channels: list[Channel], preserve_order: bool = False) -> None:
    PUBLIC_DIR.mkdir(exist_ok=True)
    ordered = channels if preserve_order else sorted(channels, key=lambda item: (item.category.lower(), item.name.lower()))

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
    max_workers = int(validation.get("max_workers", 8))
    user_agent = validation.get("user_agent", "SSIPTV-Auto-Update/1.0")
    verify_tls = bool(validation.get("verify_tls", True))

    seen: set[tuple[str, str]] = set()
    candidates: list[tuple[str, Channel]] = []
    valid_channels: list[Channel] = []
    report: list[dict] = []
    selected_channels = config.get("selected_channels") or []

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
            candidates.append((source_name, channel))

    for channel_config in config.get("dynamic_channels", []):
        source_name = channel_config.get("source", "Dynamic channel")
        try:
            channel = load_dynamic_channel(channel_config)
        except Exception as exc:
            report.append(
                {
                    "source": source_name,
                    "channel": channel_config.get("name", "<unnamed>"),
                    "category": channel_config.get("category", "Other"),
                    "url": channel_config.get("page_url"),
                    "ok": False,
                    "status": str(exc),
                }
            )
            continue

        key = channel_key(channel)
        if key not in seen:
            seen.add(key)
            candidates.append((source_name, channel))

    candidates = apply_selected_channels(candidates, selected_channels, report)
    validation_results: dict[tuple[str, str], tuple[bool, str]] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(validate_stream, channel.url, timeout, user_agent, verify_tls): (source_name, channel)
            for source_name, channel in candidates
        }

        for future in as_completed(future_map):
            source_name, channel = future_map[future]
            validation_results[channel_key(channel)] = future.result()

    for source_name, channel in candidates:
        ok, status = validation_results[channel_key(channel)]
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

    write_playlist(valid_channels, preserve_order=bool(selected_channels))
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(valid_channels)} valid channels to {PLAYLIST_PATH}")


if __name__ == "__main__":
    main()
