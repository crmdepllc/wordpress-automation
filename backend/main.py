"""Local launcher for the FastAPI app.

`python main.py` starts a dev server. In Docker we invoke uvicorn directly
(see backend/Dockerfile). The real app lives in `app/main.py`.
"""

import uvicorn


def main() -> None:
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
