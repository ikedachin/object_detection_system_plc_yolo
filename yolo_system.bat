REM For Windows
@echo off

REM Integrated Cameraを停止する
powershell -Command "Get-PnpDevice -FriendlyName 'Integrated Camera' | Disable-PnpDevice -Confirm:$false"

REM カレントディレクトリを取得
set "folder=%~dp0"

echo %folder%

REM 仮想環境をアクティベート
call %folder%yolo_system\.venv\Scripts\activate

REM ディレクトリを変更
cd %folder%yolo_system\yolo_system

REM サーバーを起動（バックグラウンドで実行）
start /B python manage.py runserver

REM 15秒待機
timeout /t 15 /nobreak > nul

REM Microsoft Edgeで指定のURLを開く
start msedge.exe --new-window "http://127.0.0.1:8000/"

REM 全画面表示のためのVBScriptを作成
echo Set WshShell = WScript.CreateObject("WScript.Shell") > "%temp%\fullscreen.vbs"
echo WScript.Sleep 3000 >> "%temp%\fullscreen.vbs"
echo WshShell.SendKeys "{F11}" >> "%temp%\fullscreen.vbs"

REM VBScriptを実行
start /wait wscript.exe "%temp%\fullscreen.vbs"

REM 一時ファイルを削除
del "%temp%\fullscreen.vbs"
