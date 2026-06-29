@echo off
echo === 업종쏠림지수 웹 시작 ===
echo.

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [오류] Python이 설치되어 있지 않습니다.
    echo https://www.python.org 에서 Python 3.11 이상을 설치하세요.
    pause
    exit /b 1
)

echo [1/2] 필요 패키지 설치 중...
pip install -r requirements.txt -q

echo [2/2] 서버 시작 중...
echo.
echo 브라우저에서 http://localhost:8000 으로 접속하세요
echo 처음 실행 시 데이터 수집에 약 3-5분 소요됩니다.
echo 종료하려면 이 창을 닫으세요.
echo.
uvicorn app:app --host 0.0.0.0 --port 8000
pause
