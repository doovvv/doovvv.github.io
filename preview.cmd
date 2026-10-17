@echo off
setlocal
echo Open http://127.0.0.1:8001/ in your browser.
echo Keep this window open. Press Ctrl+C to stop.
python -m http.server 8001 --bind 127.0.0.1 --directory "%~dp0."
pause
