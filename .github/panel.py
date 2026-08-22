#!/usr/bin/env python3
"""
Generates the profile metrics panel as an SVG.

Every figure is read through an authenticated client so private repositories
are included. A figure that cannot be read is drawn as a dash, never as zero.

Usage:
  panel.py            write metrics-*.svg next to this script's parent
  panel.py OUT.svg    write somewhere else
"""

import json
import subprocess
import sys
import urllib.parse
from collections import Counter
from datetime import date, datetime
from pathlib import Path

OWNER = "fmazmz"

def gh(args):
    r = subprocess.run(["gh", *args], capture_output=True, text=True)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return None

def search_count(q):
    n = gh(["api", f"search/issues?q={urllib.parse.quote(q)}&per_page=1",
            "--jq", ".total_count"])
    return n if isinstance(n, int) else None

def contributions_all_time():
    total = 0
    for year in range(2021, date.today().year + 1):
        q = (f'{{user(login:"{OWNER}"){{contributionsCollection('
             f'from:"{year}-01-01T00:00:00Z",to:"{year}-12-31T23:59:59Z")'
             f'{{contributionCalendar{{totalContributions}}}}}}}}')
        d = gh(["api", "graphql", "-f", f"query={q}"])
        try:
            total += d["data"]["user"]["contributionsCollection"]["contributionCalendar"]["totalContributions"]
        except (TypeError, KeyError):
            return None
    return total

def releases_count(repos):
    total = 0
    got_any = False
    for repo in repos:
        n = gh(["api", f"repos/{OWNER}/{repo['name']}/releases", "--jq", "length"])
        if isinstance(n, int):
            total += n
            got_any = True
    return total if got_any else None

def collect():
    repos = gh(["repo", "list", OWNER, "--limit", "200", "--json",
                "name,stargazerCount,forkCount,isPrivate,primaryLanguage,"
                "licenseInfo,diskUsage"]) or []
    profile = gh(["api", "graphql", "-f", f'query={{user(login:"{OWNER}"){{'
                 f"followers{{totalCount}} following{{totalCount}} "
                 f"organizations{{totalCount}} starredRepositories{{totalCount}} "
                 f"watching{{totalCount}} createdAt}}}}"])
    u = (profile or {}).get("data", {}).get("user", {}) or {}

    public = [r for r in repos if not r["isPrivate"]]
    pkgs = gh(["api", "/user/packages?package_type=npm", "--jq", "length"])
    langs = Counter(r["primaryLanguage"]["name"] for r in repos if r.get("primaryLanguage"))

    joined = u.get("createdAt")
    years = None
    if joined:
        years = round((datetime.now().date() - datetime.fromisoformat(
            joined.replace("Z", "+00:00")).date()).days / 365.25, 1)

    return {
        "years": years,
        "followers": (u.get("followers") or {}).get("totalCount"),
        "following": (u.get("following") or {}).get("totalCount"),
        "orgs": (u.get("organizations") or {}).get("totalCount"),
        "starred": (u.get("starredRepositories") or {}).get("totalCount"),
        "watching": (u.get("watching") or {}).get("totalCount"),
        "commits": contributions_all_time(),
        "prs": search_count(f"is:pr author:{OWNER}"),
        "prs_merged": search_count(f"is:pr author:{OWNER} is:merged"),
        "reviews": search_count(f"is:pr reviewed-by:{OWNER}"),
        "issues": search_count(f"is:issue author:{OWNER}"),
        "repos": len(repos) or None,
        "repos_public": len(public),
        "stars": sum(r["stargazerCount"] for r in public if r["name"] != OWNER) if repos else None,
        "forks": sum(r["forkCount"] for r in repos) if repos else None,
        "licensed": sum(1 for r in repos if r.get("licenseInfo")) if repos else None,
        "releases": releases_count(repos),
        "packages": pkgs,
        "disk": round(sum(r.get("diskUsage") or 0 for r in repos) / 1024) if repos else None,
        "languages": langs.most_common(5),
    }

def n(v):
    if v is None:
        return "–"
    return f"{v:,}" if isinstance(v, int) and v >= 1000 else str(v)

def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

THEMES = {
    "light": {"fg": "#1f2328", "muted": "#59636e", "border": "#d1d9e0"},
    "dark": {"fg": "#f0f6fc", "muted": "#9198a1", "border": "#3d444d"},
}

LANG_COLOURS = {
    "Python": "#3572A5", "TypeScript": "#3178c6", "HTML": "#e34c26",
    "JavaScript": "#f1e05a", "Swift": "#F05138", "Java": "#b07219",
    "Rust": "#dea584", "Astro": "#ff5a03", "Shell": "#89e051",
    "CSS": "#663399", "Go": "#00ADD8", "Ruby": "#701516",
}
FALLBACK_COLOUR = "#8b949e"

FONT = ('"Mona Sans VF", -apple-system, "system-ui", "Segoe UI", '
        '"Noto Sans", Helvetica, Arial, sans-serif')

def build(d, theme="dark"):
    c = THEMES[theme]
    W, H = 792, 268
    rows_left = [
        ("Contributions", n(d["commits"])),
        ("Pull requests opened", n(d["prs"])),
        ("Merged", n(d["prs_merged"])),
        ("Pull requests reviewed", n(d["reviews"])),
        ("Issues opened", n(d["issues"])),
    ]
    rows_right = [
        ("Repositories", f'{n(d["repos"])}' + (f' ({d["repos_public"]} public)' if d["repos"] else "")),
        ("Releases", n(d["releases"])),
        ("Packages", n(d["packages"])),
        ("Licensed", f'{n(d["licensed"])} of {n(d["repos"])}'),
        ("Storage", f'{n(d["disk"])} MB'),
    ]
    rows_third = [
        ("Stars received", n(d["stars"])),
        ("Forks", n(d["forks"])),
        ("Followers", n(d["followers"])),
        ("Following", n(d["following"])),
        ("Organizations", n(d["orgs"])),
    ]

    def column(rows, x, y0, label):
        out = [f'<text x="{x}" y="{y0}" class="h">{esc(label)}</text>']
        y = y0 + 32
        for k, v in rows:
            out.append(f'<text x="{x}" y="{y}" class="k">{esc(k)}</text>')
            out.append(f'<text x="{x + 264}" y="{y}" class="v" text-anchor="end">{esc(v)}</text>')
            y += 27
        return "\n".join(out)

    total_lang = sum(count for _, count in d["languages"]) or 1
    bar_w, bar_y, bar_h = W, 216, 8
    seg, cursor, legend = [], 0.0, []
    for lang, count in d["languages"]:
        colour = LANG_COLOURS.get(lang, FALLBACK_COLOUR)
        w = bar_w * count / total_lang
        seg.append(f'<rect x="{cursor:.2f}" y="{bar_y}" width="{w:.2f}" height="{bar_h}" fill="{colour}"/>')
        cursor += w
        legend.append((lang, colour))

    leg_parts, lx = [], 0
    for lang, colour in legend:
        leg_parts.append(f'<circle cx="{lx + 5}" cy="248" r="5" fill="{colour}"/>')
        leg_parts.append(f'<text x="{lx + 14}" y="252" class="lg">{esc(lang)}</text>')
        lx += 26 + len(lang) * 6.9

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<style>
.h {{ fill: {c["fg"]}; font: 600 16px {FONT}; }}
.k {{ fill: {c["muted"]}; font: 400 14px {FONT}; }}
.v {{ fill: {c["fg"]}; font: 600 14px {FONT}; font-variant-numeric: tabular-nums; }}
.lg {{ fill: {c["muted"]}; font: 400 12px {FONT}; }}
.rule {{ stroke: {c["border"]}; stroke-width: 1; }}
</style>
{column(rows_left, 0, 20, "Activity")}
{column(rows_right, 280, 20, "Repositories")}
{column(rows_third, 560, 20, "Reach")}
<line x1="0" y1="196" x2="{W}" y2="196" class="rule"/>
<text x="0" y="212" class="h">Languages</text>
<clipPath id="bar"><rect x="0" y="{bar_y}" width="{W}" height="{bar_h}" rx="4"/></clipPath>
<g clip-path="url(#bar)">
{chr(10).join(seg)}
</g>
{chr(10).join(leg_parts)}
</svg>
'''

if __name__ == "__main__":
    base = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent
    if base.suffix == ".svg":
        base = base.parent
    data = collect()
    for theme in THEMES:
        out = base.parent / f"metrics-{theme}.svg"
        out.write_text(build(data, theme))
        print(f"wrote {out}")
    missing = [k for k, v in data.items() if v is None]
    if missing:
        print(f"unreadable, drawn as dashes: {', '.join(missing)}")
