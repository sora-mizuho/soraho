"""そらほの卓記録: Notion（または同梱の見本データ）から静的サイトを作る。

使い方:
    python site/build.py            # _site/ にサイトを書き出す

環境変数 NOTION_TOKEN があれば Notion から最新データを読み込む。
なければ site/seed/ の見本データで作る（Notion 連携前の確認用）。
標準ライブラリだけで動く。
"""

import html
import json
import re
import mimetypes
import os
import shutil
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT.parent / "_site"
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
BASE = CONFIG["base_url"].rstrip("/") + "/"
NOTION_VERSION = "2022-06-28"
# 更新ごとに変わる目印。サイト内リンクに付けて、古いページの表示（キャッシュ）を避ける
V = "?v=" + time.strftime("%Y%m%d%H%M%S")
FONT_LINK = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Zen+Kaku+Gothic+New:wght@400;500;700;900&display=swap">'
)


# ---------- Notion ----------

def notion(path, body=None):
    req = urllib.request.Request(
        "https://api.notion.com/v1/" + path,
        data=json.dumps(body).encode() if body is not None else None,
        method="POST" if body is not None else "GET",
        headers={
            "Authorization": "Bearer " + os.environ["NOTION_TOKEN"],
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as res:
        return json.load(res)


def query_all(database_id):
    pages, cursor = [], None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        res = notion(f"databases/{database_id}/query", body)
        pages += res["results"]
        if not res.get("has_more"):
            return pages
        cursor = res["next_cursor"]


def text(prop):
    if not prop:
        return ""
    items = prop.get(prop["type"]) or []
    return "".join(t.get("plain_text", "") for t in items).strip()


def select(prop):
    return prop["select"]["name"] if prop and prop.get("select") else ""


def files(prop):
    urls = []
    for f in (prop or {}).get("files", []):
        urls.append(f["file"]["url"] if f["type"] == "file" else f["external"]["url"])
    return urls


def prop(pr, name):
    """欄の名前で探す。Notion 側で名前に説明を足しても見つかるよう、前方一致も許す。"""
    if name in pr:
        return pr[name]
    return next((v for k, v in pr.items() if k.startswith(name)), None)


def title_prop(pr):
    """タイトルの欄は名前が変わっても種類（title）で見つける。"""
    return next((v for v in pr.values() if v.get("type") == "title"), None)


SCENARIO_PROPS = ["ふりがな", "システム", "遊んだHO", "タグ", "所持", "PL通過", "KP/GM済み", "BOOTH"]
TOKUI_PROPS = ["分類", "度合い", "メモ"]
REPORT_PROPS = ["開催日", "システム", "KP/GM", "参加者", "一言コメント", "ネタバレ感想", "部屋画像"]


def check_props(pages, names, label):
    """Notion の欄が見つからないときは、空のサイトを公開せずに止める（今のサイトはそのまま残る）。"""
    if not pages:
        return
    pr = pages[0]["properties"]
    missing = [n for n in names if prop(pr, n) is None]
    if title_prop(pr) is None:
        missing.insert(0, "タイトル")
    if missing:
        sys.exit(
            f"エラー：Notion の「{label}」で、次の欄が見つかりません：{'、'.join(missing)}\n"
            f"欄の名前を変えた場合は、元の名前で始まるように戻してください（例：「{missing[0]}（説明）」は OK）。\n"
            "サイトは更新せず、今の状態のまま残しています。"
        )


def load_from_notion():
    scenarios = []
    scenario_pages = query_all(CONFIG["notion"]["scenarios_database_id"])
    check_props(scenario_pages, SCENARIO_PROPS, "シナリオ一覧")
    for p in scenario_pages:
        pr = p["properties"]
        name = text(title_prop(pr))
        if not name or name.startswith("【見本】"):
            continue
        scenarios.append({
            "n": name,
            "f": text(prop(pr, "ふりがな")) or name,
            "s": select(prop(pr, "システム")) or "システム未設定",
            "ho": text(prop(pr, "遊んだHO")),
            "t": [o["name"] for o in (prop(pr, "タグ") or {}).get("multi_select", [])],
            "own": bool((prop(pr, "所持") or {}).get("checkbox")),
            "pl": bool((prop(pr, "PL通過") or {}).get("checkbox")),
            "kp": bool((prop(pr, "KP/GM済み") or {}).get("checkbox")),
            "url": (prop(pr, "BOOTH") or {}).get("url") or "",
            "_nofuri": not text(prop(pr, "ふりがな")),
        })
    reports = []
    report_pages = query_all(CONFIG["notion"]["reports_database_id"])
    check_props(report_pages, REPORT_PROPS, "卓報告")
    for p in report_pages:
        pr = p["properties"]
        title = text(title_prop(pr))
        if not title:
            continue
        date = (prop(pr, "開催日") or {}).get("date") or {}
        imgs = files(prop(pr, "部屋画像"))
        cover = p.get("cover") or {}
        if not imgs and cover:
            imgs = [cover.get(cover.get("type"), {}).get("url", "")]
        reports.append({
            "id": p["id"].replace("-", ""),
            "title": title,
            "date": (date.get("start") or "")[:10],
            "end": (date.get("end") or "")[:10],
            "sys": select(prop(pr, "システム")),
            "kp": text(prop(pr, "KP/GM")),
            "players": text(prop(pr, "参加者")),
            "comment": text(prop(pr, "一言コメント")),
            "spoiler": text(prop(pr, "ネタバレ感想")),
            "image": next((u for u in imgs if u), ""),
        })
    return scenarios, reports, load_tokui_from_notion()


def load_tokui_from_notion():
    db = CONFIG["notion"].get("tokui_database_id")
    if not db:
        return []
    pages = query_all(db)
    check_props(pages, TOKUI_PROPS, "得意と苦手")
    items = []
    for p in pages:
        pr = p["properties"]
        name = text(title_prop(pr))
        if name:
            items.append({"name": name, "cat": select(prop(pr, "分類")), "level": select(prop(pr, "度合い")),
                          "memo": text(prop(pr, "メモ"))})
    return items


# プロフィール・お知らせページ：見出し2ごとに、その下の文章をまとめる
PROFILE_SPECIAL = ["ひとこと", "所持ルールブック", "SNSについて", "このサイトについて", "シナリオ一覧のお知らせ", "得意と苦手のお知らせ"]
PROFILE_BLOCKS = {"paragraph": "p", "bulleted_list_item": "li", "numbered_list_item": "li", "quote": "p"}


def rich_html(items):
    out = []
    for t in items:
        s = esc(t.get("plain_text", "")).replace("\n", "<br>")
        if (t.get("annotations") or {}).get("bold"):
            s = f"<strong>{s}</strong>"
        href = t.get("href")
        out.append(f'<a href="{esc(href)}" target="_blank" rel="noopener">{s}</a>' if href else s)
    return "".join(out).strip()


def load_profile_from_notion():
    page_id = CONFIG["notion"].get("profile_page_id")
    if not page_id:
        return None
    blocks, cursor = [], None
    try:
        while True:
            res = notion(f"blocks/{page_id}/children?page_size=100" + (f"&start_cursor={cursor}" if cursor else ""))
            blocks += res["results"]
            if not res.get("has_more"):
                break
            cursor = res["next_cursor"]
    except Exception as e:  # 読めなくてもサイトは作る（見本の文章を使う）
        print(f"注意：プロフィール・お知らせのページを読み込めませんでした（{e}）。見本の文章を使います", file=sys.stderr)
        return None
    sections, cur = {}, None
    for b in blocks:
        kind = b["type"]
        if kind in ("heading_1", "heading_2", "heading_3"):
            cur = "".join(t.get("plain_text", "") for t in b[kind]["rich_text"]).strip()
            sections.setdefault(cur, [])
        elif cur and kind in PROFILE_BLOCKS:
            h = rich_html(b[kind]["rich_text"])
            if h:
                sections[cur].append((PROFILE_BLOCKS[kind], h))
    return sections


def load_profile_seed():
    raw = json.loads((ROOT / "seed" / "profile.json").read_text(encoding="utf-8"))
    return {k: [(kind, esc(t)) for kind, t in v] for k, v in raw.items()}


def blocks_html(items):
    """段落と箇条書きを HTML にする。続く箇条書きは1つのリストにまとめる。"""
    out, lis = [], []
    for kind, h in items:
        if kind == "li":
            lis.append(f"<li>{h}</li>")
            continue
        if lis:
            out.append("<ul>" + "".join(lis) + "</ul>")
            lis = []
        out.append(f"<p>{h}</p>")
    if lis:
        out.append("<ul>" + "".join(lis) + "</ul>")
    return "".join(out)


def plain(items):
    return " ".join(re.sub(r"<[^>]+>", "", h) for _, h in items)


def load_seed():
    s = json.loads((ROOT / "seed" / "scenarios.json").read_text(encoding="utf-8"))
    r = json.loads((ROOT / "seed" / "reports.json").read_text(encoding="utf-8"))
    t = json.loads((ROOT / "seed" / "tokui.json").read_text(encoding="utf-8"))
    return s, r, t


# ---------- helpers ----------

def esc(s):
    return html.escape(s or "", quote=True)


def multiline(s):
    return "<br>".join(esc(line) for line in (s or "").splitlines())


def fmt_date(d):
    return d.replace("-", "/") if d else ""


def fmt_period(r):
    """開催日を「2026/09/20〜27」のように表示する。年や月が変わるところだけ書く。"""
    start, end = r.get("date") or "", r.get("end") or ""
    if not end or end == start:
        return fmt_date(start)
    if not start:
        return fmt_date(end)
    sy, sm, _ = start.split("-")
    ey, em, ed = end.split("-")
    if sy != ey:
        tail = fmt_date(end)
    elif sm != em:
        tail = f"{em}/{ed}"
    else:
        tail = ed
    return f"{fmt_date(start)}〜{tail}"


def slug(r):
    # Notion のページIDは先頭がワークスペース内で共通なので、末尾を使って重複を避ける
    return (r["date"].replace("-", "") or "nodate") + "-" + r["id"][-8:]


def parse_players(raw):
    rows = []
    # 1人ずつ改行、または「;」「；」で区切る（Notion のフォームは改行できないため）
    for line in re.split(r"[\n;；]", raw or ""):
        parts = [x.strip() for x in line.replace("／", "/").split("/")]
        if not any(parts):
            continue
        if len(parts) >= 3:
            rows.append({"ho": parts[0], "pl": parts[1], "pc": " / ".join(parts[2:])})
        elif len(parts) == 2:
            rows.append({"ho": "", "pl": parts[0], "pc": parts[1]})
        else:
            rows.append({"ho": "", "pl": parts[0], "pc": ""})
    return rows


def save_image(url, name):
    if not url:
        return ""
    try:
        with urllib.request.urlopen(url, timeout=60) as res:
            data = res.read()
            ctype = res.headers.get_content_type()
    except Exception as e:  # 画像が取れなくてもサイトは作る
        print(f"画像を取得できませんでした: {name}: {e}", file=sys.stderr)
        return ""
    ext = mimetypes.guess_extension(ctype) or Path(urllib.parse.urlparse(url).path).suffix or ".png"
    if ext == ".jpe":
        ext = ".jpg"
    (OUT / "img").mkdir(exist_ok=True)
    (OUT / "img" / (name + ext)).write_bytes(data)
    return "img/" + name + ext


def page(*, title, description, path, root, current, body, image="", extra_head="", scripts=""):
    full_title = title if title == CONFIG["site_title"] else f"{title}｜{CONFIG['site_title']}"
    og_image = BASE + image if image else ""
    nav = [("index.html", "ホーム", "home"), ("reports/index.html", "🎲 卓報告", "reports"),
           ("scenarios.html", "📚 シナリオ一覧", "scenarios"), ("tokui.html", "🧡 得意と苦手", "tokui")]
    cur = ' aria-current="page"'
    nav_html = "".join(
        f'<a href="{root}{href}{V}"{cur if key == current else ""}>{label}</a>' for href, label, key in nav
    )
    meta = [
        f'<meta name="description" content="{esc(description)}">',
        f'<meta property="og:title" content="{esc(full_title)}">',
        f'<meta property="og:description" content="{esc(description)}">',
        f'<meta property="og:type" content="{"article" if current == "report" else "website"}">',
        f'<meta property="og:url" content="{esc(BASE + path)}">',
        f'<meta property="og:site_name" content="{esc(CONFIG["site_title"])}">',
        f'<meta name="twitter:card" content="{"summary_large_image" if og_image else "summary"}">',
    ]
    if og_image:
        meta.append(f'<meta property="og:image" content="{esc(og_image)}">')
    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(full_title)}</title>
{chr(10).join(meta)}
{FONT_LINK}
<link rel="stylesheet" href="{root}assets/style.css{V}">
{extra_head}
</head>
<body>
<div class="wrap">
<header class="site">
  <a class="logo" href="{root}index.html{V}">{esc(CONFIG["site_title"])}</a>
  <p>{esc(CONFIG["site_description"])}</p>
</header>
<nav class="main">{nav_html}</nav>
<main>
{body}
</main>
<footer class="site">© {esc(CONFIG["profile"]["name"])}</footer>
</div>
{scripts}
</body>
</html>
"""


# ---------- pages ----------

LEVELS = [("◎", "love", "◎ 好き・得意"), ("○", "ok", "○ 大丈夫"), ("△", "weak", "△ 苦手"), ("✕", "ng", "✕ NG")]
CAT_ORDER = ["描写", "展開", "関係性", "進行・卓の雰囲気"]


def level_key(level):
    for mark, key, _ in LEVELS:
        if level.startswith(mark) or (mark == "✕" and level.startswith(("×", "x", "X"))):
            return key
    return "other" if level else ""


def build_tokui(items, profile):
    rated = [i for i in items if i["level"]]
    sections = []
    groups = [(key, label) for _, key, label in LEVELS]
    others = sorted({i["level"] for i in rated if level_key(i["level"]) == "other"})
    groups += [("other:" + o, o) for o in others]
    for key, label in groups:
        rows = [i for i in rated if (level_key(i["level"]) == key if not key.startswith("other:") else i["level"] == key[6:])]
        if not rows:
            continue
        rows.sort(key=lambda i: (CAT_ORDER.index(i["cat"]) if i["cat"] in CAT_ORDER else len(CAT_ORDER), i["cat"], i["name"]))
        cls = key if not key.startswith("other:") else "other"
        lis = "".join(
            f'<li class="tk-item"><span class="tk-name">{esc(i["name"])}</span>'
            + (f'<span class="tk-cat">{esc(i["cat"])}</span>' if i["cat"] else "")
            + (f'<span class="tk-memo">{multiline(i["memo"])}</span>' if i["memo"] else "")
            + "</li>" for i in rows)
        sections.append(f'<section class="tk-sec tk-{cls}"><h2 class="tk-head"><span class="tk-label">{esc(label)}</span>'
                        f'<span class="tk-n">{len(rows)}件</span></h2><ul class="tk-list">{lis}</ul></section>')
    intro = f'<div class="tk-intro">{blocks_html(profile.get("得意と苦手のお知らせ", []))}</div>'
    body = intro + ("".join(sections) if sections else '<p class="empty">ただいま準備中です。</p>')
    (OUT / "tokui.html").write_text(page(
        title="得意と苦手", description="TRPGで好きなこと・苦手なこと・NG（地雷）の一覧です。", path="tokui.html",
        root="", current="tokui", body=body), encoding="utf-8")


def build_home(profile):
    p = CONFIG["profile"]
    links = []
    if p.get("x"):
        links.append(f'<dt>X</dt><dd><a href="https://x.com/{esc(p["x"])}" target="_blank" rel="noopener">@{esc(p["x"])}</a></dd>')
    if p.get("mixi2"):
        links.append(f'<dt>mixi2</dt><dd><a href="https://mixi.social/@{esc(p["mixi2"])}" target="_blank" rel="noopener">@{esc(p["mixi2"])}</a></dd>')
    sns_note = profile.get("SNSについて")
    if sns_note:
        links.append(f'<dd class="note">{blocks_html(sns_note)}</dd>')
    intro = blocks_html(profile.get("ひとこと", [])) or f"<p>{multiline(p['intro'])}</p>"
    books = plain(profile.get("所持ルールブック", [])) or p["owned_books"]
    extra = "".join(
        f'<section class="about"><h2>{esc(k)}</h2>{blocks_html(v)}</section>'
        for k, v in profile.items() if k not in PROFILE_SPECIAL and v)
    site_note = profile.get("このサイトについて")
    footer_note = f'<section class="site-note"><h2>このサイトについて</h2>{blocks_html(site_note)}</section>' if site_note else ""
    body = f"""<section class="profile">
  <h1>{esc(p["name"])}</h1>
  <div class="intro">{intro}</div>
  <dl>
    <dt>所持ルールブック</dt><dd>{esc(books)}</dd>
    {"".join(links)}
  </dl>
</section>
<p class="nudge">同卓前に <a href="tokui.html{V}">🧡 得意と苦手</a> もご確認ください</p>
{f'<div class="abouts">{extra}</div>' if extra else ""}
{footer_note}"""
    (OUT / "index.html").write_text(page(
        title=CONFIG["site_title"], description=CONFIG["site_description"], path="",
        root="", current="home", body=body), encoding="utf-8")


def build_scenarios(scenarios, profile):
    data = json.dumps(scenarios, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    notice = profile.get("シナリオ一覧のお知らせ")
    body = (f'<div class="notice">{blocks_html(notice)}</div>' if notice else "") + """<div class="systems" id="systems"></div>
<div class="tools">
  <input class="search" id="q" type="search" placeholder="シナリオ名・ふりがなで探す" aria-label="シナリオを検索">
  <button class="chip" data-k="own" aria-pressed="false">所持</button>
  <button class="chip" data-k="pl" aria-pressed="true">PL通過</button>
  <button class="chip" data-k="kp" aria-pressed="false">KP/GM済み</button>
</div>
<div class="index" id="index"></div>
<div id="list"><p class="empty">シナリオ一覧を読み込んでいます…</p></div>
<button class="totop" id="totop" hidden>↑ ページの先頭へ</button>"""
    scripts = f'<script id="scenario-data" type="application/json">{data}</script>\n<script src="assets/scenarios.js{V}"></script>'
    (OUT / "scenarios.html").write_text(page(
        title="シナリオ一覧", description=f"所持・通過シナリオの一覧（{len(scenarios)}件）", path="scenarios.html",
        root="", current="scenarios", body=body, scripts=scripts), encoding="utf-8")


def build_reports(reports):
    (OUT / "reports").mkdir(exist_ok=True)
    cards = []
    for r in reports:
        s = slug(r)
        img = r.get("_img", "")
        cover = f'<img class="cover" src="../{esc(img)}" alt="" loading="lazy">' if img else '<div class="cover"></div>'
        meta = " ".join(f"<span>{esc(x)}</span>" for x in [fmt_period(r), r["sys"], ("KP：" + r["kp"]) if r["kp"] else ""] if x)
        cards.append(f'<a class="card" href="{s}.html{V}">{cover}<div class="body"><span class="t">{esc(r["title"])}</span><span class="d">{meta}</span></div></a>')

        players = parse_players(r["players"])
        has_ho = any(p["ho"] for p in players)
        table = ""
        if players:
            head = ("<th>HO</th>" if has_ho else "") + "<th>PL</th><th>探索者</th>"
            rows = "".join(
                "<tr>" + (f"<td>{esc(p['ho'])}</td>" if has_ho else "") + f"<td>{esc(p['pl'])}</td><td>{esc(p['pc'])}</td></tr>"
                for p in players)
            table = f'<section><h2>参加者</h2><div class="tablewrap"><table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div></section>'
        facts = "".join(f"<dt>{k}</dt><dd>{esc(v)}</dd>" for k, v in [("開催日", fmt_period(r)), ("システム", r["sys"]), ("KP/GM", r["kp"])] if v)
        comment = f'<section><h2>ひとこと</h2><p class="comment">{multiline(r["comment"])}</p></section>' if r["comment"] else ""
        spoiler = f'<details class="spoiler"><summary>⚠️ ネタバレ感想</summary><div class="in">{multiline(r["spoiler"])}</div></details>' if r["spoiler"] else ""
        hero = f'<img class="hero" src="../{esc(img)}" alt="{esc(r["title"])}の部屋画像">' if img else ""
        body = f"""<article class="report">
  <a class="back" href="index.html{V}">← 卓報告の一覧へ</a>
  {hero}
  <h1>{esc(r["title"])}</h1>
  <dl class="facts">{facts}</dl>
  {table}
  {comment}
  {spoiler}
</article>"""
        desc = (r["comment"].splitlines() or [""])[0] or f'{fmt_period(r)} {r["sys"]}'.strip()
        (OUT / "reports" / f"{s}.html").write_text(page(
            title=r["title"], description=desc, path=f"reports/{s}.html", root="../", current="report",
            body=body, image=img), encoding="utf-8")

    listing = f'<div class="cards">{"".join(cards)}</div>' if cards else '<p class="empty">まだ卓報告はありません。</p>'
    (OUT / "reports" / "index.html").write_text(page(
        title="卓報告", description=f"卓報告の一覧（{len(reports)}件）", path="reports/index.html",
        root="../", current="reports", body=listing), encoding="utf-8")


def main():
    if os.environ.get("NOTION_TOKEN"):
        print("Notion からデータを読み込みます")
        scenarios, reports, tokui = load_from_notion()
        profile = load_profile_from_notion()
    else:
        print("NOTION_TOKEN がないため、見本データでサイトを作ります")
        scenarios, reports, tokui = load_seed()
        profile = None
    if profile is None:
        profile = load_profile_seed()
    reports.sort(key=lambda r: r["date"] or "", reverse=True)

    if not scenarios:
        sys.exit("エラー：シナリオが1件も読み込めませんでした。サイトは更新せず、今の状態のまま残しています。")
    for s in scenarios:
        if s.pop("_nofuri", False) and not s["n"].isascii():
            print(f"注意：「{s['n']}」のふりがなが空です（50音順の並びがずれます）", file=sys.stderr)
        if s["s"] == "システム未設定":
            print(f"注意：「{s['n']}」のシステムが空です（「システム未設定」タブに出ます）", file=sys.stderr)

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    shutil.copytree(ROOT / "assets", OUT / "assets")
    (OUT / ".nojekyll").write_text("")
    for r in reports:
        r["_img"] = save_image(r.get("image", ""), slug(r))

    build_home(profile)
    build_scenarios(scenarios, profile)
    build_reports(reports)
    build_tokui(tokui, profile)
    print(f"完了: シナリオ {len(scenarios)} 件、卓報告 {len(reports)} 件 → {OUT}")


if __name__ == "__main__":
    main()
