"""
scraper.py  ―  キャッシュの読み書きと列名正規化のみ担当
スクレイピング処理は scrape_worker.py が行う
"""
import json
from pathlib import Path

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


def load_cache(cache_path: Path) -> dict:
    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_cache(cache: dict, cache_path: Path):
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
