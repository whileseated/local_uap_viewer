#!/usr/bin/env python3
import csv
import html
import json
import re
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / ".dvids-cache"
OUT = ROOT / "index.html"
DATA_OUT = ROOT / "uap-local-index.json"
RELEASE_DIR_PATTERN = re.compile(r"^release_(\d+)$")
REPETITIVE_DESCRIPTION_PREFIX = (
    "On March 6, 2026, eight members of the U.S. House of Representatives requested access to 51 "
    "potentially UAP-related records allegedly held by the Department of War and the Intelligence "
    "Community. The All-domain Anomaly Resolution Office (AARO) identified a collection of responsive "
    "materials held on a classified network. Many of these materials lack a substantiated chain-of-custody."
)


def text_between(pattern, value, default=""):
    match = re.search(pattern, value, re.IGNORECASE | re.DOTALL)
    if not match:
        return default
    return html.unescape(match.group(1)).strip()


def clean_text(value):
    value = html.unescape(value or "")
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n\s+", "\n", value)
    return value.strip()


def trim_description(value):
    value = clean_text(value)
    if value.startswith(REPETITIVE_DESCRIPTION_PREFIX):
        value = value[len(REPETITIVE_DESCRIPTION_PREFIX):].lstrip()
    return value


def table_value(label, body):
    pattern = rf"<td>\s*{re.escape(label)}:\s*</td>\s*<td>(.*?)</td>"
    return clean_text(text_between(pattern, body))


def slug_from_title(title):
    slug = re.sub(r"[^A-Za-z0-9\-_ ]+", "", title or "").strip()
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug


def normalize_record_title(title):
    def pad_pr(match):
        return f"DOW-UAP-PR{int(match.group(1)):03d}"

    return re.sub(r"\bDOW-UAP-PR0*([0-9]+)\b", pad_pr, title or "", flags=re.IGNORECASE)


def parse_search_cache(dod_id):
    path = CACHE_DIR / f"{dod_id}.html"
    if not path.exists():
        return {}

    body = path.read_text(errors="replace")
    title = text_between(r'<meta\s+property="og:title"\s+content="([^"]+)"', body)
    if not title:
        title = text_between(r'<title>\s*DVIDS\s*-\s*Video\s*-\s*([^<]+)</title>', body)
    if not title:
        title = text_between(r'<div\s+class="image--basic"[^>]+title="([^"]+)"', body)
    if not title:
        title = text_between(r'<div\s+class="mobile-search-info">\s*<h1>([^<]+)</h1>', body)

    dvids_url = text_between(r'<meta\s+property="og:url"\s+content="([^"]+)"', body)
    if not dvids_url:
        href = text_between(r'href="(/video/[0-9]+[^"]*)"', body)
        if href:
            dvids_url = "https://www.dvidshub.net" + href

    poster = text_between(r'<meta\s+property="og:image"\s+content="([^"]+)"', body)
    if not poster or "dvids_logo" in poster:
        poster = text_between(r'<img[^>]+src="([^"]*thumbs/frames/video/[^"]+)"', body)
        poster = poster.replace("/122x92_", "/1000w_")
    description = text_between(r'<meta\s+property="og:description"\s+content="([^"]*)"', body)
    mp4_url = text_between(r'<source\s+src="([^"]+\.mp4)"', body)
    if not mp4_url:
        mp4_url = f"https://d34w7g4gy10iej.cloudfront.net/video/2605/{dod_id}/{dod_id}.mp4"

    dvids_id = ""
    id_match = re.search(r"/video/([0-9]+)", dvids_url)
    if id_match:
        dvids_id = id_match.group(1)

    detail_path = CACHE_DIR / "details" / f"{dvids_id}.html" if dvids_id else None
    detail_body = detail_path.read_text(errors="replace") if detail_path and detail_path.exists() else ""
    if detail_body:
        title = text_between(r'<meta\s+property="og:title"\s+content="([^"]+)"', detail_body) or title
        description = text_between(r'<meta\s+property="og:description"\s+content="([^"]*)"', detail_body) or description
        poster = text_between(r'<meta\s+property="og:image"\s+content="([^"]+)"', detail_body) or poster
        mp4_url = text_between(r'<source\s+src="([^"]+\.mp4)"', detail_body) or mp4_url

    title = normalize_record_title(clean_text(title))
    pr_match = re.search(r"\bDOW-UAP-PR0*([0-9]+)\b", title, re.IGNORECASE)
    pr = f"PR{int(pr_match.group(1)):03d}" if pr_match else ""

    war_hash = ""
    if title:
        war_hash = "https://www.war.gov/UFO/#" + slug_from_title(title)

    return {
        "title": title,
        "description": trim_description(description),
        "dvids_url": dvids_url,
        "dvids_id": dvids_id,
        "poster": poster,
        "source_mp4_url": mp4_url,
        "pr": pr,
        "war_url": war_hash,
        "date_taken": table_value("Date Taken", detail_body),
        "date_posted": table_value("Date Posted", detail_body),
        "location": table_value("Location", detail_body),
        "virin": table_value("VIRIN", detail_body),
        "duration": table_value("Length", detail_body),
        "category": table_value("Category", detail_body),
    }


def csv_metadata_by_dod():
    candidates = [
        ROOT / "uap-csv.csv",
        ROOT / "uap-data.csv",
        ROOT / "uap-release001.csv",
    ]
    rows = {}
    for path in candidates:
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                joined = " ".join(str(v) for v in row.values())
                for dod_id in set(re.findall(r"DOD_[0-9]+", joined)):
                    rows[dod_id] = row
    return rows


def file_size(size):
    units = ["B", "KB", "MB", "GB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024


def records():
    csv_rows = csv_metadata_by_dod()
    items = []
    release_dirs = sorted(
        [path for path in ROOT.iterdir() if path.is_dir() and RELEASE_DIR_PATTERN.match(path.name)],
        key=lambda path: path.name,
    )
    video_paths = []
    for release_dir in release_dirs:
        video_paths.extend(sorted(release_dir.glob("*.mp4")))
    video_paths.extend(sorted(ROOT.glob("*.mp4")))

    for path in video_paths:
        dod_match = re.search(r"DOD_[0-9]+", path.name)
        dod_id = dod_match.group(0) if dod_match else path.stem
        release_match = RELEASE_DIR_PATTERN.match(path.parent.name)
        release_id = f"release_{release_match.group(1)}" if release_match else "unfiled"
        release_label = f"Release {int(release_match.group(1)):02d}" if release_match else "Unfiled"
        item = {
            "filename": path.name,
            "path": path.relative_to(ROOT).as_posix(),
            "release": release_id,
            "release_label": release_label,
            "dod_id": dod_id,
            "size": path.stat().st_size,
            "size_label": file_size(path.stat().st_size),
            "mtime": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
        }
        item.update(parse_search_cache(dod_id))
        if dod_id in csv_rows:
            item["csv"] = csv_rows[dod_id]
        if not item.get("title"):
            item["title"] = dod_id
            item["description"] = "No cached DVIDS metadata found yet."
        items.append(item)
    return items


def render(items):
    data = json.dumps(items, ensure_ascii=True).replace("</", "<\\/")
    count = len(items)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Local UAP Video Index</title>
  <style>
    :root {{ color-scheme: dark; --bg:#111314; --panel:#191d1f; --line:#30363a; --text:#f1f3f2; --muted:#a7b0ad; --accent:#69c7b7; --warn:#e5b769; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--bg); color:var(--text); font:15px/1.45 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
    header {{ position:sticky; top:0; z-index:2; background:rgba(17,19,20,.94); border-bottom:1px solid var(--line); backdrop-filter: blur(10px); }}
    .wrap {{ max-width:1440px; margin:0 auto; padding:18px; }}
    h1 {{ margin:0 0 12px; font-size:24px; letter-spacing:0; }}
    .controls {{ display:grid; grid-template-columns:minmax(220px,1fr) auto auto auto; gap:10px; align-items:center; }}
    input, select, button {{ min-height:38px; border:1px solid var(--line); border-radius:6px; background:#0d0f10; color:var(--text); padding:0 10px; font:inherit; }}
    button {{ cursor:pointer; }}
    .filter-row {{ display:grid; grid-template-columns:auto 1fr; gap:10px; align-items:start; margin-top:12px; }}
    .filter-label {{ color:var(--muted); font-size:12px; line-height:30px; text-transform:uppercase; letter-spacing:.08em; }}
    .filter-pills {{ display:flex; flex-wrap:wrap; gap:8px; }}
    .filter-pill {{ min-height:30px; border-radius:999px; padding:0 10px; color:var(--muted); }}
    .filter-pill.active {{ border-color:var(--accent); color:var(--text); background:#14302c; }}
    .summary {{ color:var(--muted); font-size:13px; margin-top:10px; }}
    main {{ max-width:1440px; margin:0 auto; padding:18px; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(430px,1fr)); gap:14px; }}
    article {{ border:1px solid var(--line); border-radius:8px; background:var(--panel); overflow:hidden; }}
    video {{ display:block; width:100%; aspect-ratio:16/9; background:#050606; }}
    .body {{ padding:14px; }}
    .kicker {{ display:flex; flex-wrap:wrap; gap:8px; margin-bottom:8px; color:var(--muted); font:12px/1.2 ui-monospace,SFMono-Regular,Menlo,monospace; }}
    h2 {{ margin:0; font-size:17px; line-height:1.3; letter-spacing:0; }}
    p {{ margin:10px 0 0; color:var(--muted); }}
    .description {{ white-space:pre-line; }}
    .links {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:12px; }}
    a {{ color:var(--accent); text-decoration:none; }}
    a:hover {{ text-decoration:underline; }}
    .pill {{ border:1px solid var(--line); border-radius:999px; padding:4px 8px; font-size:12px; color:var(--muted); }}
    .missing {{ color:var(--warn); }}
    @media (max-width:760px) {{
      .controls {{ grid-template-columns:1fr; }}
      .grid {{ grid-template-columns:1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="wrap">
      <h1>Local UAP Video Index</h1>
      <div class="controls">
        <input id="q" type="search" placeholder="Search title, DOD id, PR number, description...">
        <select id="sort">
          <option value="title">Sort by title</option>
          <option value="size_desc">Largest files first</option>
          <option value="size_asc">Smallest files first</option>
          <option value="dod">Sort by DOD id</option>
        </select>
        <button id="collapse">Pause all</button>
        <button id="clear">Clear</button>
      </div>
      <div class="filter-row">
        <div class="filter-label">Release</div>
        <div id="releases" class="filter-pills" aria-label="View by release"></div>
      </div>
      <div class="filter-row">
        <div class="filter-label">Decade</div>
        <div id="decades" class="filter-pills" aria-label="View by decade"></div>
      </div>
      <div class="summary"><span id="shown">{count}</span> of {count} local MP4s shown. Generated {html.escape(now)}. Metadata comes from cached DVIDS search pages when available; official War.gov hash links are reconstructed from DVIDS titles.</div>
    </div>
  </header>
  <main><div id="grid" class="grid"></div></main>
  <script id="records" type="application/json">{data}</script>
  <script>
    const records = JSON.parse(document.getElementById('records').textContent);
    const grid = document.getElementById('grid');
    const q = document.getElementById('q');
    const sort = document.getElementById('sort');
    const shown = document.getElementById('shown');
    const releases = document.getElementById('releases');
    const decades = document.getElementById('decades');
    const resultsTop = document.querySelector('main');
    let activeRelease = '';
    let activeDecade = '';
    const esc = value => String(value || '').replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
    function decadeOf(r) {{
      const match = String(r.date_taken || '').match(/(\\d{{4}})$/);
      if (!match) return 'Unknown';
      return `${{Math.floor(Number(match[1]) / 10) * 10}}s`;
    }}
    function renderDecades() {{
      const counts = records.reduce((acc, r) => {{
        const decade = decadeOf(r);
        acc[decade] = (acc[decade] || 0) + 1;
        return acc;
      }}, {{}});
      const labels = Object.keys(counts).sort((a, b) => {{
        if (a === 'Unknown') return 1;
        if (b === 'Unknown') return -1;
        return Number(b.slice(0, 4)) - Number(a.slice(0, 4));
      }});
      decades.innerHTML = [`<button class="filter-pill ${{activeDecade ? '' : 'active'}}" type="button" data-decade="">All (${{records.length}})</button>`]
        .concat(labels.map(label => `<button class="filter-pill ${{activeDecade === label ? 'active' : ''}}" type="button" data-decade="${{esc(label)}}">${{esc(label.replace('s', ''))}} (${{counts[label]}})</button>`))
        .join('');
    }}
    function renderReleases() {{
      const counts = records.reduce((acc, r) => {{
        const key = r.release || 'unfiled';
        if (!acc[key]) acc[key] = {{ label: r.release_label || 'Unfiled', count: 0 }};
        acc[key].count += 1;
        return acc;
      }}, {{}});
      const keys = Object.keys(counts).sort((a, b) => counts[a].label.localeCompare(counts[b].label));
      releases.innerHTML = [`<button class="filter-pill ${{activeRelease ? '' : 'active'}}" type="button" data-release="">All (${{records.length}})</button>`]
        .concat(keys.map(key => `<button class="filter-pill ${{activeRelease === key ? 'active' : ''}}" type="button" data-release="${{esc(key)}}">${{esc(counts[key].label)}} (${{counts[key].count}})</button>`))
        .join('');
    }}
    function card(r) {{
      const hay = [r.title, r.dod_id, r.pr, r.description, r.filename].join(' ');
      const links = [
        r.dvids_url && `<a class="pill" href="${{esc(r.dvids_url)}}" target="_blank" rel="noreferrer">DVIDS</a>`,
        r.war_url && `<a class="pill" href="${{esc(r.war_url)}}" target="_blank" rel="noreferrer">War.gov record</a>`,
        r.source_mp4_url && `<a class="pill" href="${{esc(r.source_mp4_url)}}" target="_blank" rel="noreferrer">Source MP4</a>`
      ].filter(Boolean).join('');
      const facts = [
        r.date_taken && `Taken ${{esc(r.date_taken)}}`,
        r.date_posted && `Posted ${{esc(r.date_posted)}}`,
        r.location && `Location ${{esc(r.location)}}`,
        r.duration && `Length ${{esc(r.duration)}}`,
        r.virin && `VIRIN ${{esc(r.virin)}}`
      ].filter(Boolean).map(v => `<span class="pill">${{v}}</span>`).join('');
      return `<article data-hay="${{esc(hay.toLowerCase())}}">
        <video controls preload="metadata" playsinline poster="${{esc(r.poster || '')}}">
          <source src="${{esc(r.path)}}" type="video/mp4">
        </video>
        <div class="body">
          <div class="kicker">
            <span>${{esc(r.pr || 'No PR')}}</span>
            <span>${{esc(r.release_label || 'Unfiled')}}</span>
            <span>${{esc(r.dod_id)}}</span>
            <span>${{esc(r.size_label)}}</span>
            ${{r.dvids_id ? `<span>DVIDS ${{esc(r.dvids_id)}}</span>` : '<span class="missing">metadata not cached</span>'}}
          </div>
          <h2>${{esc(r.title)}}</h2>
          ${{facts ? `<div class="links">${{facts}}</div>` : ''}}
          ${{r.description ? `<p class="description">${{esc(r.description)}}</p>` : ''}}
          <div class="links"><a class="pill" href="${{esc(r.path)}}">Open local MP4</a>${{links}}</div>
        </div>
      </article>`;
    }}
    function scrollToResults() {{
      const target = resultsTop.getBoundingClientRect().top + window.scrollY - 12;
      window.scrollTo({{ top: Math.max(0, target), behavior: 'smooth' }});
    }}
    function render(shouldScroll = false) {{
      const term = q.value.trim().toLowerCase();
      let list = records.filter(r => {{
        const matchesTerm = !term || [r.title, r.dod_id, r.pr, r.description, r.filename].join(' ').toLowerCase().includes(term);
        const matchesRelease = !activeRelease || r.release === activeRelease;
        const matchesDecade = !activeDecade || decadeOf(r) === activeDecade;
        return matchesTerm && matchesRelease && matchesDecade;
      }});
      list.sort((a,b) => {{
        if (sort.value === 'size_desc') return b.size - a.size;
        if (sort.value === 'size_asc') return a.size - b.size;
        if (sort.value === 'dod') return a.dod_id.localeCompare(b.dod_id);
        return a.title.localeCompare(b.title);
      }});
      shown.textContent = list.length;
      grid.innerHTML = list.map(card).join('');
      renderReleases();
      renderDecades();
      if (shouldScroll) scrollToResults();
    }}
    q.addEventListener('input', () => render(true));
    sort.addEventListener('change', () => render(true));
    decades.addEventListener('click', event => {{
      const button = event.target.closest('[data-decade]');
      if (!button) return;
      activeDecade = button.dataset.decade;
      render(true);
    }});
    releases.addEventListener('click', event => {{
      const button = event.target.closest('[data-release]');
      if (!button) return;
      activeRelease = button.dataset.release;
      render(true);
    }});
    document.getElementById('clear').addEventListener('click', () => {{ q.value = ''; activeRelease = ''; activeDecade = ''; render(true); }});
    document.getElementById('collapse').addEventListener('click', () => document.querySelectorAll('video').forEach(v => v.pause()));
    render();
  </script>
</body>
</html>
"""


def main():
    items = records()
    DATA_OUT.write_text(json.dumps(items, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    OUT.write_text(render(items), encoding="utf-8")
    cached = sum(1 for item in items if item.get("dvids_id"))
    print(f"Wrote {OUT.name} with {len(items)} videos ({cached} with cached DVIDS metadata).")
    print(f"Wrote {DATA_OUT.name}.")


if __name__ == "__main__":
    main()
