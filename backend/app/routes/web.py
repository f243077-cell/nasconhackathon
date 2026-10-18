"""Guest Web Player (FR-4.2, spec II 1.1/6.2): static assets + every /web/* page served from index.html."""
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, Response

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
router = APIRouter()


@router.get("/web/{path:path}", include_in_schema=False)
def guest_web(path: str):
    if not (WEB_DIR / "index.html").exists():
        return Response(status_code=404)
    return FileResponse(WEB_DIR / "index.html", media_type="text/html",
                        headers={"Cache-Control": "no-cache"})
