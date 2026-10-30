"""One-Command Server Startup for Vietnamese Stock Market Advisor & Prediction System.
Runs the FastAPI ASGI server on http://127.0.0.1:8000.
"""

import sys
from pathlib import Path
import uvicorn

# Ensure repository root is on sys.path
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def main():
    """Starts the Uvicorn server serving the application and SPA frontend."""
    banner = """
    ======================================================================
       VN-Advisor | Vietnamese Stock Market Advisor & Prediction System
       Dark OLED Financial Terminal (Circular 120/2020/TT-BTC Compliant)
    ======================================================================
    [+] Server running at: http://127.0.0.1:8000
    [+] Interactive Docs:  http://127.0.0.1:8000/docs
    [+] Alternative Docs:  http://127.0.0.1:8000/redoc
    [+] Press Ctrl+C to stop the server
    ======================================================================
    """
    print(banner)

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        log_level="info",
        access_log=True,
    )


if __name__ == "__main__":
    main()
