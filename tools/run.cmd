@echo off
setlocal
chcp 65001 >nul
pushd "%~dp0.."
python -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 (
  set "BLOG_PYTHON=python"
  goto run
)
py -3 -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 (
  set "BLOG_PYTHON=py -3"
  goto run
)
echo Python 3.10 or newer is required. Install Python and try again.
popd
exit /b 1
:run
%BLOG_PYTHON% tools\blog.py %*
set "BLOG_RESULT=%errorlevel%"
popd
exit /b %BLOG_RESULT%
