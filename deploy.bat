@echo off
chcp 65001 > nul
echo ===================================
echo  農薬データをGitHubに反映します
echo ===================================

:: pesticide_cache.json を docs フォルダにコピー
copy /Y "pesticide_cache.json" "docs\pesticide_cache.json"
echo [1/3] データをコピーしました

:: git add / commit / push
git add docs/
git commit -m "データ更新"
git push origin main
echo [2/3] GitHubに送信しました

echo.
echo ===================================
echo  完了！iPhoneで反映されます
echo  (Wi-Fi接続時に自動更新されます)
echo ===================================
pause
