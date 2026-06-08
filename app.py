"""
app.py  ―  農薬適用作物検索アプリ（Streamlit）
起動方法: python -m streamlit run app.py
"""
import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

from scraper import load_cache

# ──────────────────────────────────────────────
# ページ設定
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="農薬適用作物検索",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    h1 { color: #2d6a4f; }
    .stButton > button { border-radius: 6px; }
    .stDataFrame { font-size: 0.88rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ──────────────────────────────────────────────
# パス設定
# ──────────────────────────────────────────────
APP_DIR    = Path(__file__).parent
CSV_PATH   = APP_DIR / "在庫表 - 農薬クロード用.csv"
CACHE_PATH = APP_DIR / "pesticide_cache.json"
WORKER     = APP_DIR / "scrape_worker.py"

RESULT_COLUMNS = [
    "農薬名", "適用作物名", "対象病害虫・雑草名",
    "希釈倍数", "使用液量", "使用時期", "本剤の使用回数", "使用方法",
]
COLUMN_LABELS = {
    "農薬名":           "農薬名",
    "適用作物名":       "作物名",
    "対象病害虫・雑草名": "対象病害虫・雑草",
    "希釈倍数":         "希釈倍数",
    "使用液量":         "使用液量",
    "使用時期":         "使用時期",
    "本剤の使用回数":   "使用回数",
    "使用方法":         "使用方法",
}


# ──────────────────────────────────────────────
# ヘルパー関数
# ──────────────────────────────────────────────
@st.cache_data
def load_inventory(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df.columns = ["農薬名", "登録番号"]
    df["農薬名"]   = df["農薬名"].str.strip()
    df["登録番号"] = df["登録番号"].astype(str).str.strip()
    return df


def run_worker(mode: str, progress_bar, status_text) -> bool:
    """scrape_worker.py を別プロセスで実行し、進捗を表示する"""
    try:
        proc = subprocess.Popen(
            [sys.executable, str(WORKER), str(CSV_PATH), str(CACHE_PATH), mode],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        for line in proc.stdout:
            line = line.strip()
            if line.startswith("PROGRESS:"):
                parts = line.split(":", 3)
                if len(parts) >= 4:
                    try:
                        i, total = int(parts[1]), int(parts[2])
                        name = parts[3]
                        progress_bar.progress(i / total)
                        status_text.text(f"取得中 ({i}/{total}): {name}")
                    except Exception:
                        pass
            elif line == "DONE":
                break
            elif line.startswith("ERROR"):
                st.warning(f"⚠️ {line}")
        proc.wait()
        return proc.returncode == 0
    except Exception as e:
        st.error(f"ワーカー起動エラー: {e}")
        return False


def search(crop_name: str, cache: dict) -> pd.DataFrame:
    crop_query = crop_name.strip().lower()
    if not crop_query:
        return pd.DataFrame()
    rows = []
    for reg_num, entry in cache.items():
        for record in entry.get("適用表", []):
            if crop_query in record.get("適用作物名", "").lower():
                row = {"農薬名": entry.get("農薬名", ""), "登録番号": reg_num}
                row.update(record)
                rows.append(row)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    cols = [c for c in RESULT_COLUMNS if c in df.columns]
    df = df[cols + ["登録番号"]].copy()
    sort_cols = [c for c in ["農薬名", "適用作物名"] if c in df.columns]
    return df.sort_values(sort_cols)


# ──────────────────────────────────────────────
# メイン
# ──────────────────────────────────────────────
def main():
    if not CSV_PATH.exists():
        st.error(f"CSVファイルが見つかりません: {CSV_PATH}")
        st.info("アプリと同じフォルダに「在庫表 - 農薬クロード用.csv」を置いてください。")
        return

    inventory_df = load_inventory(str(CSV_PATH))
    cache        = load_cache(CACHE_PATH)

    cached_regs  = set(cache.keys())
    all_regs     = set(inventory_df["登録番号"].astype(str))
    missing_regs = all_regs - cached_regs

    # ──────────── SIDEBAR ────────────
    with st.sidebar:
        st.title("⚙️ 操作パネル")

        col_a, col_b = st.columns(2)
        col_a.metric("在庫農薬", f"{len(inventory_df)} 品目")
        col_b.metric("取得済み", f"{len(cached_regs)} 品目")

        if missing_regs:
            st.warning(f"未取得: {len(missing_regs)} 品目")
        else:
            st.success("全データ取得済み ✅")

        with st.expander("📦 在庫農薬一覧"):
            for _, row in inventory_df.iterrows():
                reg = str(row["登録番号"]).strip()
                if reg in cache:
                    cnt = cache[reg].get("取得件数", 0)
                    st.write(f"✅ {row['農薬名']} ({cnt}件)")
                else:
                    st.write(f"⬜ {row['農薬名']}")

        st.divider()
        st.subheader("🔄 データ取得")

        if st.button("🔄 全農薬を再取得", use_container_width=True):
            pb  = st.progress(0.0)
            msg = st.empty()
            ok  = run_worker("all", pb, msg)
            if ok:
                st.cache_data.clear()
                st.success("✅ 取得完了！")
                st.rerun()

        btn_label = f"📥 未取得のみ取得 ({len(missing_regs)} 品目)"
        if st.button(btn_label, use_container_width=True, disabled=not missing_regs):
            pb2  = st.progress(0.0)
            msg2 = st.empty()
            ok   = run_worker("missing", pb2, msg2)
            if ok:
                st.cache_data.clear()
                st.success(f"✅ {len(missing_regs)} 品目を追加しました")
                st.rerun()

        st.divider()
        with st.expander("📖 使い方"):
            st.markdown("""
            **初回**: 「🔄 全農薬を再取得」をクリック（数分かかります）

            **検索**: 作物名を入力（部分一致）

            **農薬追加**: CSVに行を追加 → 「📥 未取得のみ取得」
            """)

    # ──────────── MAIN AREA ────────────
    st.title("🌱 農薬適用作物検索")
    st.caption("手持ち農薬の中から、指定した作物に使える農薬と適用情報を表示します")

    if not cache:
        st.info("👈 左のサイドバーの **「🔄 全農薬を再取得」** でデータを取得してください。")
        return

    col1, col2 = st.columns([5, 1])
    with col1:
        crop_name = st.text_input(
            "作物名",
            placeholder="例: トマト、きゅうり、なす、いちご...",
            label_visibility="collapsed",
        )
    with col2:
        st.button("🔍 検索", type="primary", use_container_width=True)

    if not crop_name.strip():
        st.markdown("---")
        st.markdown("作物名を入力して検索してください（例: `トマト`、`きゅうり`）")
        return

    results_df = search(crop_name, cache)

    if results_df.empty:
        st.warning(f"「{crop_name}」に適用できる農薬は手持ちの中にありませんでした。")
        if missing_regs:
            st.info(f"※ {len(missing_regs)} 品目はまだデータ未取得です。")
        return

    unique_n = results_df["農薬名"].nunique()
    st.success(f"「{crop_name}」に使える農薬: **{unique_n} 品目** / **{len(results_df)} 件**")

    view_mode = st.radio("", ["📋 全件一覧", "🗂️ 農薬別タブ"], horizontal=True,
                         label_visibility="collapsed")

    disp = results_df.drop(columns=["登録番号"], errors="ignore")
    cols = [c for c in RESULT_COLUMNS if c in disp.columns]
    disp = disp[cols].rename(columns=COLUMN_LABELS)
    disp = disp.loc[:, (disp != "").any(axis=0)].reset_index(drop=True)

    if view_mode == "📋 全件一覧":
        st.dataframe(disp, use_container_width=True, hide_index=True,
                     height=min(700, 45 + len(disp) * 36))
    else:
        names = results_df["農薬名"].unique().tolist()
        for tab, name in zip(st.tabs(names), names):
            with tab:
                sub = disp[disp["農薬名"] == name].drop(columns=["農薬名"], errors="ignore")
                st.dataframe(sub.reset_index(drop=True), use_container_width=True, hide_index=True)

    csv_bytes = disp.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
    st.download_button("📥 CSVダウンロード", csv_bytes,
                       file_name=f"農薬検索_{crop_name}.csv", mime="text/csv")


if __name__ == "__main__":
    main()
