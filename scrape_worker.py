#!/usr/bin/env python3
"""
scrape_worker.py  ―  別プロセスとして実行されるスクレイピングワーカー
app.py から subprocess 経由で呼び出される
使い方: python scrape_worker.py <csv_path> <cache_path> <mode>
  mode: "all" または "missing"
"""
import json
import sys
import time
from pathlib import Path

import pandas as pd
from playwright.sync_api import sync_playwright

# ─────────────── 設定 ───────────────
TARGET_KEYWORDS = ["作物", "病害虫", "希釈", "使用時期", "使用方法", "使用回数"]

COLUMN_KEYWORD_MAP = {
    "適用作物名":         ["作物名", "適用作物名", "適用作物"],
    "対象病害虫・雑草名": ["病害虫", "雑草", "対象病害虫", "適用病害虫"],
    "希釈倍数":          ["希釈倍数", "希釈倍率", "倍数"],
    "使用液量":          ["使用液量", "液量", "10a当たり"],
    "使用時期":          ["使用時期"],
    "本剤の使用回数":     ["使用回数", "回数"],
    "使用方法":          ["使用方法", "散布方法"],
    "備考":              ["備考"],
}


# ─────────────── ヘルパー関数 ───────────────
def normalize_row(raw: dict) -> dict:
    result = {k: "" for k in COLUMN_KEYWORD_MAP}
    used = set()
    for std_col, keywords in COLUMN_KEYWORD_MAP.items():
        for k, v in raw.items():
            if k in used:
                continue
            if any(kw in k for kw in keywords):
                result[std_col] = str(v).strip()
                used.add(k)
                break
    return result


def load_cache(path: Path) -> dict:
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_cache(cache: dict, path: Path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def extract_table(page) -> list[dict]:
    tables = page.query_selector_all("table")
    if not tables:
        return []

    best_table, best_score = None, 0
    for table in tables:
        hs = table.query_selector_all("thead th, thead td") or \
             table.query_selector_all("tr:first-child th, tr:first-child td")
        texts = [h.inner_text().strip() for h in hs]
        score = sum(1 for kw in TARGET_KEYWORDS if any(kw in t for t in texts))
        if score > best_score:
            best_score, best_table = score, table

    if not best_table or best_score < 1:
        return []

    rows = best_table.query_selector_all("tr")
    headers, results = [], []
    for row in rows:
        cells = [" ".join(c.inner_text().strip().split())
                 for c in row.query_selector_all("td, th")]
        if not cells or all(c == "" for c in cells):
            continue
        if not headers:
            if any(kw in " ".join(cells) for kw in TARGET_KEYWORDS):
                headers = cells
        else:
            rd = {headers[j]: cells[j] if j < len(cells) else "" for j in range(len(headers))}
            if any(rd.values()):
                results.append(rd)
    return results


def scrape_one(page, reg_num: str) -> list[dict]:
    url = f"https://pesticide.maff.go.jp/agricultural-chemicals/details/{reg_num}"
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(1500)

        for sel in ["text=適用表情報", "a:has-text('適用表情報')",
                    "button:has-text('適用表情報')", "li:has-text('適用表情報')"]:
            try:
                elem = page.query_selector(sel)
                if elem:
                    elem.click()
                    page.wait_for_timeout(2000)
                    break
            except Exception:
                continue

        try:
            page.wait_for_selector("table", timeout=10_000)
        except Exception:
            pass

        all_rows = extract_table(page)
        seen = {frozenset(r.items()) for r in all_rows}

        for _ in range(50):
            nxt = None
            for sel in ["text=次へ", "a:has-text('次へ')", "button:has-text('次へ')"]:
                try:
                    e = page.query_selector(sel)
                    if e and e.get_attribute("disabled") is None and \
                       e.get_attribute("aria-disabled") != "true":
                        nxt = e
                        break
                except Exception:
                    continue
            if not nxt:
                break
            nxt.click()
            page.wait_for_timeout(1500)
            added = 0
            for r in extract_table(page):
                key = frozenset(r.items())
                if key not in seen:
                    seen.add(key)
                    all_rows.append(r)
                    added += 1
            if added == 0:
                break

        return all_rows
    except Exception as e:
        print(f"ERROR {reg_num}: {e}", file=sys.stderr, flush=True)
        return []


# ─────────────── メイン ───────────────
def main():
    if len(sys.argv) < 3:
        print("引数不足: csv_path cache_path [mode]", file=sys.stderr)
        sys.exit(1)

    csv_path   = Path(sys.argv[1])
    cache_path = Path(sys.argv[2])
    mode       = sys.argv[3] if len(sys.argv) > 3 else "all"

    df = pd.read_csv(csv_path)
    df.columns = ["農薬名", "登録番号"]
    df["農薬名"]   = df["農薬名"].str.strip()
    df["登録番号"] = df["登録番号"].astype(str).str.strip()

    cache = load_cache(cache_path)

    if mode == "missing":
        cached = set(cache.keys())
        df = df[~df["登録番号"].isin(cached)]

    total = len(df)
    if total == 0:
        print("DONE", flush=True)
        return

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        )
        page = ctx.new_page()

        for i, (_, row) in enumerate(df.iterrows()):
            name = str(row["農薬名"]).strip()
            reg  = str(row["登録番号"]).strip()

            # 進捗をstdoutに出力（app.py が読み取る）
            print(f"PROGRESS:{i+1}:{total}:{name}", flush=True)

            rows = scrape_one(page, reg)
            normalized = [normalize_row(r) for r in rows]

            cache[reg] = {
                "農薬名": name,
                "登録番号": reg,
                "適用表": normalized,
                "取得件数": len(normalized),
            }
            save_cache(cache, cache_path)
            time.sleep(1.5)

        browser.close()

    print("DONE", flush=True)


if __name__ == "__main__":
    main()
