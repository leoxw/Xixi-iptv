#!/usr/bin/env python3
"""从 xixitv.live 的公开接口同步直播源，生成播放列表。

数据源：GET https://xixitv.live/api/config
这是 xixitv.live 前端自己使用的接口，无需登录，返回全部频道：
每条频道含 name / group / logo / url，部分含 sources[] 备用线路。

生成文件：
- playlist.m3u   全部频道（主线路 + 每条备用线路各一条目）
- direct.m3u     只有第三方 HLS 直链的频道，可被普通播放器直接播放
- cntv.m3u       只有站内 /cntv/live/*.m3u8 的央视频道（见 README 的限制说明）
- channels.json  规范化后的频道数据（地址均为绝对地址）

只用 Python 标准库。生成内容不写时间戳，频道没变化时文件不会产生 diff。
"""

import json
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urljoin

BASE = "https://xixitv.live/"
CONFIG_URL = "https://xixitv.live/api/config"
ROOT = Path(__file__).resolve().parent


def fetch_config() -> dict:
    req = urllib.request.Request(
        CONFIG_URL,
        headers={"User-Agent": "Mozilla/5.0 (xixitv-sources sync)", "Cache-Control": "no-store"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def absolute(url: str) -> str:
    return urljoin(BASE, url or "")


def normalize(channels: list[dict]) -> list[dict]:
    out = []
    for ch in channels:
        item = {
            "id": ch.get("id", ""),
            "name": ch.get("name", ""),
            "group": ch.get("group", ""),
            "logo": ch.get("logo", ""),
            "url": absolute(ch.get("url", "")),
            "sources": [
                {"label": s.get("label", ""), "url": absolute(s.get("url", ""))}
                for s in (ch.get("sources") or [])
            ],
        }
        out.append(item)
    return out


def is_cntv(item: dict) -> bool:
    return item["url"].startswith("https://xixitv.live/cntv/")


def is_direct(item: dict) -> bool:
    return item["url"].startswith("http") and not item["url"].startswith("https://xixitv.live/")


def extinf(item: dict, name_suffix: str = "") -> str:
    name = item["name"] + name_suffix
    return (
        f'#EXTINF:-1 tvg-id="{item["id"]}" tvg-logo="{item["logo"]}" '
        f'group-title="{item["group"]}",{name}'
    )


def write_m3u(path: Path, entries: list[tuple[dict, str, str]]) -> None:
    """entries: (item, display_suffix, url)"""
    lines = ["#EXTM3U"]
    for item, suffix, url in entries:
        lines.append(extinf(item, suffix))
        lines.append(url)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    config = fetch_config()
    channels = normalize(config.get("channels") or [])
    if not channels:
        print("接口没有返回任何频道，已中止，未改动现有文件。", file=sys.stderr)
        return 1

    (ROOT / "channels.json").write_text(
        json.dumps(channels, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # 全部：主线路 + 备用线路
    all_entries: list[tuple[dict, str, str]] = []
    for item in channels:
        all_entries.append((item, "", item["url"]))
        for s in item["sources"]:
            label = s["label"] or "备用"
            all_entries.append((item, f" [{label}]", s["url"]))
    write_m3u(ROOT / "playlist.m3u", all_entries)

    # 可直连的第三方 HLS
    write_m3u(
        ROOT / "direct.m3u",
        [(item, "", item["url"]) for item in channels if is_direct(item)],
    )

    # 站内央视源
    write_m3u(
        ROOT / "cntv.m3u",
        [(item, "", item["url"]) for item in channels if is_cntv(item)],
    )

    total_sources = sum(len(i["sources"]) for i in channels)
    print(
        f"同步完成：{len(channels)} 个频道，{total_sources} 条备用线路；"
        f"直链 {sum(1 for i in channels if is_direct(i))} 个，"
        f"站内央视源 {sum(1 for i in channels if is_cntv(i))} 个。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
