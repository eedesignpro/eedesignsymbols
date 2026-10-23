"""Self-contained static HTML gallery for a set of rendered SVGs.

Opens from ``file://``. No server, no build step, no rasterizer. One entry
per symbol library file; an entry can hold more than one SVG, one per unit
and body style, and the detail pane stacks all of them.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GalleryEntry:
    """One symbol library file's worth of rendered SVGs.

    ``svg_paths`` may be empty. ``error`` holds the export failure, if any,
    so a broken input is visible in the gallery rather than silently absent.
    """

    name: str
    category: str
    svg_paths: Sequence[Path] = field(default_factory=list)
    error: str | None = None


SVG_DISPLAY_SCALE = 2.0
"""Detail-pane image size, as a multiple of the SVG's own natural size."""


_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
  body {{
    font-family: monospace; background: #111; color: #ddd; margin: 0; padding: 1rem;
  }}
  h1 {{ color: #fff; margin: 0 0 0.5rem 0; font-size: 1.1rem; }}
  #toolbar {{
    display: flex; gap: 1rem; align-items: center; margin-bottom: 1rem; flex-wrap: wrap;
  }}
  #jump-input {{
    background: #222; color: #eee; border: 1px solid #555; padding: 0.25rem 0.5rem;
  }}
  #category-select {{
    background: #222; color: #eee; border: 1px solid #555;
    padding: 0.25rem 0.5rem; min-width: 280px;
  }}
  .sym-card {{
    border: 1px solid #444; padding: 0.4rem 0.6rem;
    margin-bottom: 0.3rem; cursor: pointer;
  }}
  .sym-card.selected {{ border-color: #8af; background: #1a2030; }}
  .sym-card.has-error {{ border-left: 4px solid #f55; }}
  #detail {{ position: fixed; top: 0; right: 0; width: 55vw; height: 100vh;
             background: #181818; border-left: 2px solid #444;
             overflow-y: auto; padding: 1rem; display: none; box-sizing: border-box; }}
  #detail.open {{ display: block; }}
  #detail img {{ max-width: 100%; height: auto; display: block; margin: 0.5rem 0;
                 background: #fff; border: 1px solid #333; }}
  .unit-label {{ color: #8af; font-size: 0.85rem; margin-top: 0.75rem; }}
  .error-text {{ color: #f77; white-space: pre-wrap; }}
  .pager {{ margin-top: 1rem; display: flex; gap: 0.5rem; align-items: center; }}
  .pager button {{
    background: #333; color: #ccc; border: 1px solid #555;
    padding: 0.3rem 0.8rem; cursor: pointer;
  }}
  .pager button:disabled {{ opacity: 0.35; cursor: default; }}
</style>
</head>
<body>
<h1>{title}</h1>
<div id="toolbar">
  <select id="category-select" onchange="selectCategoryByIndex(this.selectedIndex)"></select>
  <span id="page-info"></span>
  <input id="jump-input" type="text" placeholder="jump to name..." size="40">
  <button onclick="doJump()">Go</button>
</div>
<div id="pages"></div>
<div class="pager">
  <button id="btn-prev" onclick="changeCategory(-1)">&#8592; Prev category</button>
  <button id="btn-next" onclick="changeCategory(+1)">Next category &#8594;</button>
</div>
<div id="detail">
  <button onclick="closeDetail()" style="float:right">&#x2715; Close</button>
  <div id="detail-content"></div>
</div>

<script>
const CATEGORIES = {data_json};
const SVG_DISPLAY_SCALE = {svg_scale};

let currentCat = 0;
let selectedIdx = -1;

function init() {{
  const sel = document.getElementById("category-select");
  CATEGORIES.forEach((c, i) => {{
    const opt = document.createElement("option");
    opt.textContent = c.name + "  (" + c.items.length + ")";
    opt.value = String(i);
    sel.appendChild(opt);
  }});
  renderCategory(0);
  document.addEventListener("keydown", onKey);
}}

function renderCategory(c) {{
  currentCat = c;
  const cat = CATEGORIES[c];
  document.getElementById("category-select").selectedIndex = c;
  const container = document.getElementById("pages");
  container.innerHTML = "";
  document.getElementById("page-info").textContent =
    "Category " + (c + 1) + " / " + CATEGORIES.length +
    ": " + cat.name + " (" + cat.items.length + " symbols)";

  document.getElementById("btn-prev").disabled = c === 0;
  document.getElementById("btn-next").disabled = c >= CATEGORIES.length - 1;

  cat.items.forEach((item, i) => {{
    const card = document.createElement("div");
    card.className = "sym-card" + (item.error ? " has-error" : "") +
      (i === selectedIdx ? " selected" : "");
    card.id = "card-" + i;
    card.innerHTML = "<b>" + escHtml(item.name) + "</b>" +
      (item.error ? " <em>[export failed]</em>" : " (" + item.svg_paths.length + ")");
    card.onclick = () => openDetail(i, item);
    container.appendChild(card);
  }});
}}

function changeCategory(delta) {{
  const next = currentCat + delta;
  if (next < 0 || next >= CATEGORIES.length) return;
  selectedIdx = -1;
  renderCategory(next);
  closeDetail();
}}

function selectCategoryByIndex(i) {{
  selectedIdx = -1;
  renderCategory(i);
  closeDetail();
}}

function openDetail(idx, item) {{
  selectedIdx = idx;
  const el = document.getElementById("detail");
  el.classList.add("open");

  let body = "<h2>" + escHtml(item.name) + "</h2>";
  if (item.error) {{
    body += "<p class=\\"error-text\\">" + escHtml(item.error) + "</p>";
  }}
  if (item.svg_paths.length === 0 && !item.error) {{
    body += "<p><em>No SVG produced</em></p>";
  }}
  item.svg_paths.forEach(p => {{
    body += "<div class=\\"unit-label\\">" + escHtml(p.split(/[\\\\/]/).pop()) + "</div>";
    body += "<img src=\\"" + escHtml(p) + "\\" alt=\\"" + escHtml(item.name) +
      "\\" onload=\\"sizeDetailImg(this)\\">";
  }});
  document.getElementById("detail-content").innerHTML = body;

  renderCategory(currentCat);
}}

function sizeDetailImg(img) {{
  // Natural size x SVG_DISPLAY_SCALE, clamped to the detail pane's own width.
  const pane = document.getElementById("detail");
  const paneStyle = getComputedStyle(pane);
  const padL = parseFloat(paneStyle.paddingLeft) || 0;
  const padR = parseFloat(paneStyle.paddingRight) || 0;
  const usable = pane.clientWidth - padL - padR;
  const target = Math.min(img.naturalWidth * SVG_DISPLAY_SCALE, usable);
  img.style.width = target + "px";
}}

function closeDetail() {{
  document.getElementById("detail").classList.remove("open");
  selectedIdx = -1;
  renderCategory(currentCat);
}}

function moveSelection(delta) {{
  const items = CATEGORIES[currentCat].items;
  const next = (selectedIdx < 0) ? (delta > 0 ? 0 : items.length - 1) : selectedIdx + delta;
  if (next < 0 || next >= items.length) return;
  openDetail(next, items[next]);
  const card = document.getElementById("card-" + next);
  if (card) card.scrollIntoView({{block: "nearest"}});
}}

function doJump() {{
  const query = document.getElementById("jump-input").value.trim().toLowerCase();
  if (!query) return;
  for (let ci = 0; ci < CATEGORIES.length; ci++) {{
    const items = CATEGORIES[ci].items;
    for (let i = 0; i < items.length; i++) {{
      if (items[i].name.toLowerCase().includes(query)) {{
        renderCategory(ci);
        openDetail(i, items[i]);
        const card = document.getElementById("card-" + i);
        if (card) card.scrollIntoView({{block: "center"}});
        return;
      }}
    }}
  }}
  alert("Not found: " + query);
}}

function onKey(e) {{
  const tag = document.activeElement ? document.activeElement.tagName : "";
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
  if (e.key === "j" || e.key === "ArrowDown") moveSelection(+1);
  else if (e.key === "k" || e.key === "ArrowUp") moveSelection(-1);
  else if (e.key === "PageDown") changeCategory(+1);
  else if (e.key === "PageUp") changeCategory(-1);
  else if (e.key === "Escape") closeDetail();
}}

function escHtml(s) {{
  return String(s)
    .replace(/&/g,"&amp;").replace(/</g,"&lt;")
    .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}}

init();
</script>
</body>
</html>
"""


def build_gallery(
    entries: Sequence[GalleryEntry],
    output_path: Path,
    *,
    title: str = "Symbol Preview Gallery",
) -> Path:
    """Write a self-contained HTML gallery to ``output_path``.

    Every SVG path in ``entries`` is written as a path relative to
    ``output_path``'s own directory, so the page keeps working if the whole
    output tree is moved as a unit.

    Args:
        entries: One entry per symbol library file.
        output_path: Where to write the gallery HTML file.
        title: Page title and heading.

    Returns:
        ``output_path``, for chaining into a print statement.
    """
    output_path = Path(output_path)
    base_dir = output_path.parent

    by_category: dict[str, list[dict[str, object]]] = {}
    for entry in entries:
        record: dict[str, object] = {
            "name": entry.name,
            "error": entry.error,
            "svg_paths": [
                os.path.relpath(p, base_dir).replace("\\", "/") for p in entry.svg_paths
            ],
        }
        by_category.setdefault(entry.category, []).append(record)

    categories = [{"name": name, "items": items} for name, items in sorted(by_category.items())]

    html = _HTML_TEMPLATE.format(
        title=title,
        data_json=json.dumps(categories),
        svg_scale=SVG_DISPLAY_SCALE,
    )

    base_dir.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path


__all__ = ["SVG_DISPLAY_SCALE", "GalleryEntry", "build_gallery"]
