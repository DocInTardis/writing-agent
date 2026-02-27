# -*- coding: utf-8 -*-
"""Cnki Open Access Download command utility.

This script is part of the writing-agent operational toolchain.
"""

import argparse
import json
import hashlib
import re
import sys
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

CNKI_HOME = "https://kns.cnki.net/kns8/"
EDGE_USER_DATA = r"%LOCALAPPDATA%\Microsoft\Edge\User Data"
CHROME_USER_DATA = r"%LOCALAPPDATA%\Google\Chrome\User Data"


def main() -> int:
    parser = argparse.ArgumentParser(description="Open CNKI and optionally attempt open-access downloads.")
    parser.add_argument("--query", default="", help="Search keyword to prefill (optional).")
    parser.add_argument("--queries", default="", help="Comma-separated queries for batch collection.")
    parser.add_argument("--queries-file", default="", help="Text file with one query per line.")
    parser.add_argument("--auto", action="store_true", help="Attempt to click visible download links.")
    parser.add_argument("--collect", action="store_true", help="Collect multiple reader screenshots from search results.")
    parser.add_argument("--per-query", type=int, default=2, help="Max reader captures per query.")
    parser.add_argument("--max-shots", type=int, default=8, help="Max total screenshots across all queries.")
    parser.add_argument("--browser", choices=["edge", "chrome", "chromium"], default="chromium", help="Browser channel.")
    parser.add_argument("--use-default-profile", action="store_true", help="Reuse local browser profile for login state.")
    parser.add_argument("--profile-dir", default="Default", help="Profile directory name (e.g., Default, Profile 1).")
    parser.add_argument(
        "--login-wait",
        type=int,
        default=60,
        help="Seconds to wait for manual login when auto-download finds nothing.",
    )
    parser.add_argument("--wait", type=int, default=None, help="Seconds to wait before auto-closing (default: 10s if non-interactive).")
    parser.add_argument("--out-dir", default=".data/out/cnki_downloads", help="Directory to save downloads.")
    parser.add_argument(
        "--read-screenshot",
        action="store_true",
        help="Open a reader view if download is unavailable and save a screenshot.",
    )
    parser.add_argument(
        "--full-page",
        action="store_true",
        help="Capture full page when taking screenshots (larger files).",
    )
    parser.add_argument(
        "--capture-text",
        action="store_true",
        help="Capture visible reader text alongside screenshots.",
    )
    parser.add_argument(
        "--ocr",
        action="store_true",
        help="Run OCR on screenshots when text capture is insufficient.",
    )
    parser.add_argument(
        "--ingest",
        action="store_true",
        help="Ingest captured text into the local user library for RAG.",
    )
    parser.add_argument("--library-dir", default=".data/library", help="User library directory.")
    parser.add_argument("--rag-dir", default=".data/rag", help="RAG index directory.")
    parser.add_argument("--manual-capture", action="store_true", help="Capture screenshots from currently open pages.")
    parser.add_argument("--manual-wait", type=int, default=60, help="Seconds to wait for manual browsing before capture.")
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        url = CNKI_HOME
        if args.query:
            url = CNKI_HOME
        webbrowser.open(url)
        print("Playwright not installed; opened CNKI in default browser.")
        print("If you need automation, install Playwright and browsers, then rerun this script.")
        return 1

    def resolve_user_data_dir() -> str | None:
        if args.browser == "edge":
            return Path(EDGE_USER_DATA).expanduser().resolve().as_posix()
        if args.browser == "chrome":
            return Path(CHROME_USER_DATA).expanduser().resolve().as_posix()
        return None

    def load_queries() -> list[str]:
        queries: list[str] = []
        if args.query:
            queries.append(args.query.strip())
        if args.queries:
            queries.extend([q.strip() for q in args.queries.split(",") if q.strip()])
        if args.queries_file:
            q_path = Path(args.queries_file)
            if q_path.exists():
                for line in q_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                    q = line.strip()
                    if q:
                        queries.append(q)
        return [q for q in queries if q]

    def slugify(text: str) -> str:
        s = (text or "").strip().lower()
        s = re.sub(r"[^a-z0-9]+", "-", s)
        base = s.strip("-")
        if base:
            return base
        seed = (text or "cnki").encode("utf-8", errors="ignore")
        h = hashlib.md5(seed).hexdigest()[:6]
        return f"cnki-{h}"

    with sync_playwright() as p:
        browser_type = p.chromium
        channel = None
        if args.browser == "edge":
            channel = "msedge"
        elif args.browser == "chrome":
            channel = "chrome"

        if args.use_default_profile and channel:
            user_data_dir = resolve_user_data_dir()
            if user_data_dir and Path(user_data_dir).exists():
                context = browser_type.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    channel=channel,
                    headless=False,
                    accept_downloads=True,
                    viewport={"width": 900, "height": 700},
                    args=["--window-size=900,700", f"--profile-directory={args.profile_dir}"],
                )
            else:
                context = browser_type.launch_persistent_context(
                    user_data_dir="",
                    channel=channel,
                    headless=False,
                    accept_downloads=True,
                    viewport={"width": 900, "height": 700},
                    args=["--window-size=900,700"],
                )
        else:
            browser = browser_type.launch(headless=False, channel=channel, args=["--window-size=900,700"])
            context = browser.new_context(accept_downloads=True, viewport={"width": 900, "height": 700})

        page = context.new_page()
        page.goto(CNKI_HOME, wait_until="domcontentloaded", timeout=60000)

        def attempt_download() -> int:
            # Best-effort: click the first visible download link if any.
            saved = 0
            try:
                page.wait_for_timeout(2000)
                for sel in ["text=PDF下载", "text=下载", "a:has-text('PDF')", "a:has-text('下载')"]:
                    loc = page.locator(sel)
                    if loc.count() > 0 and loc.first.is_visible():
                        out_dir = Path(args.out_dir)
                        out_dir.mkdir(parents=True, exist_ok=True)
                        with page.expect_download(timeout=15000) as download_info:
                            loc.first.click()
                        download = download_info.value
                        target = out_dir / download.suggested_filename
                        download.save_as(target.as_posix())
                        print(f"Saved: {target}")
                        saved += 1
                        break
            except Exception:
                pass
            return saved

        def attempt_open_reader(target_page):
            # Best-effort: click a visible reading link and return the reader page.
            try:
                target_page.wait_for_timeout(2000)
                selectors = [
                    "text=在线阅读",
                    "text=阅读",
                    "text=HTML阅读",
                    "text=CAJ阅读",
                    "a:has-text('在线阅读')",
                    "a:has-text('阅读')",
                ]
                for sel in selectors:
                    loc = target_page.locator(sel)
                    if loc.count() > 0 and loc.first.is_visible():
                        try:
                            with target_page.expect_popup(timeout=15000) as popup_info:
                                loc.first.click()
                            read_page = popup_info.value
                        except Exception:
                            loc.first.click()
                            read_page = target_page
                        try:
                            read_page.wait_for_timeout(2000)
                        except Exception:
                            pass
                        return read_page
            except Exception:
                pass
            return None

        def save_reader_screenshot(read_page, *, name: str) -> Path | None:
            out_dir = Path(args.out_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            target = out_dir / f"{name}.png"
            try:
                try:
                    read_page.wait_for_load_state("domcontentloaded", timeout=8000)
                except Exception:
                    pass
                read_page.screenshot(path=target.as_posix(), full_page=bool(args.full_page))
                print(f"Saved reader screenshot: {target}")
                return target
            except Exception as exc:
                print(f"Screenshot failed: {exc}")
                try:
                    read_page.screenshot(path=target.as_posix())
                    print(f"Saved reader screenshot: {target}")
                    return target
                except Exception as exc2:
                    print(f"Failed to capture reader screenshot: {exc2}")
            return None

        ocr_engine = None

        def save_text(name: str, text: str, *, suffix: str = "") -> Path | None:
            cleaned = re.sub(r"[ \t]+", " ", str(text or ""))
            cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
            if not cleaned:
                return None
            out_dir = Path(args.out_dir) / "texts"
            out_dir.mkdir(parents=True, exist_ok=True)
            text_path = out_dir / f"{name}{suffix}.txt"
            text_path.write_text(cleaned, encoding="utf-8")
            return text_path

        def capture_text(read_page, *, name: str) -> tuple[Path | None, str]:
            if not (args.capture_text or args.ingest):
                return None, ""
            try:
                text = read_page.evaluate("() => document.body ? document.body.innerText : ''")
            except Exception:
                text = ""
            return save_text(name, text), str(text or "")

        def ocr_text_from_image(image_path: Path) -> str:
            nonlocal ocr_engine
            if not args.ocr:
                return ""
            try:
                if ocr_engine is None:
                    from rapidocr_onnxruntime import RapidOCR

                    ocr_engine = RapidOCR()
            except Exception:
                return ""
            try:
                result = ocr_engine(str(image_path))
            except Exception:
                return ""
            if isinstance(result, tuple):
                result = result[0]
            texts: list[str] = []
            if isinstance(result, list):
                for item in result:
                    if not item:
                        continue
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        t = item[1]
                        if isinstance(t, (list, tuple)):
                            t = t[0] if t else ""
                        if isinstance(t, str):
                            texts.append(t)
            return "\n".join(t for t in texts if t)

        def save_meta(*, name: str, query: str, url: str, title: str, text_path: Path | None, image_path: Path | None) -> None:
            out_dir = Path(args.out_dir) / "meta"
            out_dir.mkdir(parents=True, exist_ok=True)
            meta = {
                "name": name,
                "query": query,
                "url": url,
                "title": title,
                "text_path": str(text_path or ""),
                "image_path": str(image_path or ""),
                "captured_at": datetime.now(timezone.utc).isoformat(),
            }
            (out_dir / f"{name}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        def collect_result_links(target_page, *, limit: int) -> list[str]:
            js = """() => {
                const anchors = Array.from(document.querySelectorAll('a'));
                const out = [];
                const seen = new Set();
                const origin = location.origin;
                function normalize(href) {
                    if (!href) return '';
                    if (href.startsWith('//')) return 'https:' + href;
                    if (href.startsWith('/')) return origin + href;
                    return href;
                }
                function push(href) {
                    const url = normalize(href);
                    if (!url) return;
                    if (!url.includes('kns.cnki.net')) return;
                    if (!/detail|kcms/i.test(url)) return;
                    if (seen.has(url)) return;
                    seen.add(url);
                    out.push(url);
                }
                for (const a of anchors) {
                    const href = a.getAttribute('href') || '';
                    const dataHref = a.getAttribute('data-href') || a.getAttribute('data-url') || '';
                    const onclick = a.getAttribute('onclick') || '';
                    push(href);
                    push(dataHref);
                    if (onclick) {
                        const m = onclick.match(/(https?:\\/\\/[^'\"\\s]+)|'([^']+)'|\"([^\"]+)\"/);
                        if (m) {
                            push(m[1] || m[2] || m[3] || '');
                        }
                    }
                    if (out.length >= %d) break;
                }
                return out;
            }""" % (limit,)
            try:
                links = target_page.evaluate(js)
                if isinstance(links, list):
                    return [str(x) for x in links if x]
            except Exception:
                pass
            return []

        def ingest_records(records: list[dict]) -> None:
            if not records:
                return
            try:
                repo_root = Path(__file__).resolve().parents[1]
                repo_root_str = repo_root.as_posix()
                if repo_root_str not in sys.path:
                    sys.path.insert(0, repo_root_str)
                from writing_agent.v2.rag.index import RagIndex
                from writing_agent.v2.rag.user_library import UserLibrary
            except Exception:
                print("RAG modules not available; skip ingest.")
                return
            rag_index = RagIndex(Path(args.rag_dir))
            user_library = UserLibrary(Path(args.library_dir), rag_index)
            for rec in records:
                text_path = Path(rec.get("text_path") or "")
                if not text_path.exists():
                    continue
                text = text_path.read_text(encoding="utf-8", errors="replace").strip()
                if not text:
                    continue
                title = rec.get("title") or rec.get("name") or "cnki"
                source_id = rec.get("url") or rec.get("name") or ""
                user_library.put_text(text=text, title=title, source="cnki_reader", status="approved", source_id=source_id)

        if args.manual_capture:
            if args.query:
                try:
                    page.locator("input[type=search], input#txt_SearchText, input[name=txt_SearchText]").first.fill(args.query)
                    page.keyboard.press("Enter")
                except Exception:
                    pass
            if args.manual_wait and args.manual_wait > 0:
                page.wait_for_timeout(args.manual_wait * 1000)
            records: list[dict] = []
            total_shots = 0
            for p in list(context.pages):
                if total_shots >= max(1, args.max_shots):
                    break
                try:
                    url = p.url
                except Exception:
                    url = ""
                if not url or url in {"about:blank", ":"}:
                    continue
                try:
                    title = p.title()
                except Exception:
                    title = ""
                name = f"manual_{total_shots + 1:02d}"
                image_path = save_reader_screenshot(p, name=name) if args.read_screenshot else None
                text_path, raw_text = capture_text(p, name=name)
                if (not text_path or len(raw_text.strip()) < 200) and image_path:
                    ocr_text = ocr_text_from_image(image_path)
                    ocr_path = save_text(name, ocr_text, suffix="_ocr")
                    if ocr_path:
                        text_path = ocr_path
                if image_path or text_path:
                    save_meta(
                        name=name,
                        query=args.query or "",
                        url=str(url or ""),
                        title=title,
                        text_path=text_path,
                        image_path=image_path,
                    )
                    records.append(
                        {
                            "name": name,
                            "query": args.query or "",
                            "url": str(url or ""),
                            "title": title,
                            "text_path": str(text_path or ""),
                        }
                    )
                    total_shots += 1
            if args.ingest:
                ingest_records(records)

        elif args.collect:
            queries = load_queries()
            if not queries:
                queries = ["管理信息系统", "系统设计", "数据库设计", "测试与结果分析"]
            total_shots = 0
            records: list[dict] = []
            for q in queries:
                if total_shots >= max(1, args.max_shots):
                    break
                page.goto(CNKI_HOME, wait_until="domcontentloaded", timeout=60000)
                try:
                    page.locator("input[type=search], input#txt_SearchText, input[name=txt_SearchText]").first.fill(q)
                    page.keyboard.press("Enter")
                except Exception:
                    pass
                page.wait_for_timeout(3500)
                want = max(1, args.per_query)
                links = collect_result_links(page, limit=want * 5)
                if not links:
                    continue
                for link in links:
                    if total_shots >= max(1, args.max_shots):
                        break
                    detail = context.new_page()
                    try:
                        detail.goto(link, wait_until="domcontentloaded", timeout=60000)
                    except Exception:
                        detail.close()
                        continue
                    read_page = attempt_open_reader(detail)
                    try:
                        if read_page and read_page.is_closed():
                            read_page = None
                    except Exception:
                        pass
                    target = read_page or detail
                    try:
                        title = target.title()
                    except Exception:
                        title = ""
                    name = f"{slugify(q)}_{total_shots + 1:02d}"
                    image_path = save_reader_screenshot(target, name=name) if args.read_screenshot else None
                    text_path, raw_text = capture_text(target, name=name)
                    if (not text_path or len(raw_text.strip()) < 200) and image_path:
                        ocr_text = ocr_text_from_image(image_path)
                        ocr_path = save_text(name, ocr_text, suffix="_ocr")
                        if ocr_path:
                            text_path = ocr_path
                    if image_path or text_path:
                        save_meta(
                            name=name,
                            query=q,
                            url=str(getattr(target, "url", "") or ""),
                            title=title,
                            text_path=text_path,
                            image_path=image_path,
                        )
                        records.append(
                            {
                                "name": name,
                                "query": q,
                                "url": str(getattr(target, "url", "") or ""),
                                "title": title,
                                "text_path": str(text_path or ""),
                            }
                        )
                        total_shots += 1
                    try:
                        if read_page and read_page is not detail:
                            read_page.close()
                    except Exception:
                        pass
                    try:
                        detail.close()
                    except Exception:
                        pass
                    if total_shots >= max(1, args.max_shots):
                        break
            if args.ingest:
                ingest_records(records)

        elif args.auto:
            saved = attempt_download()
            if saved == 0:
                print("No download detected. If login is required, please login in the opened browser.")
                if args.login_wait and args.login_wait > 0:
                    print(f"Waiting {args.login_wait}s for manual login...")
                    page.wait_for_timeout(args.login_wait * 1000)
                elif sys.stdin and sys.stdin.isatty():
                    print("Press Enter to continue after login...")
                    try:
                        input()
                    except (KeyboardInterrupt, EOFError):
                        pass
                attempt_download()
                if args.read_screenshot:
                    read_page = attempt_open_reader(page)
                    if read_page is not None:
                        save_reader_screenshot(read_page, name="cnki_reader")

        if args.wait is None:
            if sys.stdin and sys.stdin.isatty():
                print("CNKI opened. Complete search/download manually if needed, then press Enter to exit.")
                try:
                    input()
                except KeyboardInterrupt:
                    pass
            else:
                page.wait_for_timeout(10000)
        else:
            if args.wait > 0:
                page.wait_for_timeout(args.wait * 1000)
        context.close()
        try:
            browser.close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
