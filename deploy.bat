@echo off
chcp 65001 > nul
echo ===================================
echo  農薬データ更新 ＆ iPhone反映
echo ===================================
echo.

:: スクレイピング実行
echo [1/3] データを取得中...（数分かかります）
python scrape_worker.py "在庫表 - 農薬クロード用.csv" pesticide_cache.json all
if %errorlevel% neq 0 (
    echo エラー: データ取得に失敗しました
    pause
    exit /b 1
)
echo [1/3] データ取得完了！
echo.

:: docs フォルダにコピー
echo [2/3] データをコピー中...
copy /Y "pesticide_cache.json" "docs\pesticide_cache.json" > nul
echo [2/3] コピー完了！
echo.

:: GitHub に送信
echo [3/3] iPhoneに反映中...
git add docs/pesticide_cache.json
git commit -m "データ更新"
git push origin master
echo [3/3] 送信完了！
echo.

echo ===================================
echo  完了！
echo  iPhoneをWi-Fiに繋いでアプリを
echo  開くと最新データに更新されます
echo ===================================
pause
