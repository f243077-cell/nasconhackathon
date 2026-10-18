# Guest Web Player (`/web/*`)

Static HTML/CSS/JS, no build step, no CDN (hls.js 1.5.15 vendored, Apache-2.0; Barlow fonts, SIL OFL).
Owner: Huzaifa. Served by `routes/web.py` (Tanzeel).

## What `routes/web.py` needs to do

- `GET /web/static/{path}` → files in this folder (`app.js`, `styles.css`, `vendor/`, `fonts/`).
- `GET /web/{anything}` (every page: `matches/{id}/live|preview|vod|notice`, `costream/{id}`,
  `players/{id}`, `clubs/{id}`) → `index.html`. `app.js` reads the path and renders the right view.

```python
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
router = APIRouter()

@router.get("/web/{path:path}", include_in_schema=False)
def guest_web(path: str):
    return FileResponse(WEB_DIR / "index.html", media_type="text/html")

# in main.py, BEFORE include_router(web.router):
# app.mount("/web/static", StaticFiles(directory=WEB_DIR), name="web-static")
```

## API the page calls

| Call | Used for | If it's missing |
|---|---|---|
| `GET /audit/v1/score/{match_id}` (no auth) | Score banner on load and on every live message | — (Day 1 route) |
| `WS /ws/matches/{match_id}` | Live updates. Any message refreshes the score; messages carrying `home.score`/`away.score` (or `home_score`/`away_score`) are applied directly. `type: "chat_message"` messages are appended to chat. | Falls back to SSE, then polls the score every 400 ms |
| `GET /api/v1/matches/{id}/stream` (SSE) | Same as WS | Polling |
| `POST /api/v1/guest/token` → `{guest_token}` | Guest bearer for reads and for the blocked write | Page still works; the chat send still opens the auth modal |
| `GET /api/v1/matches/{id}` (guest bearer) | Team names, league name, venue, `pinned_product`, `playback_url` | Names fall back to the club ids; pinned item defaults to `prod-jersey-001` / `var-jersey-001-L` |
| `POST /api/v1/chat` `{room_id, chat_room_id, text}` | Chat send. Guest → must return **403 `GUEST_WRITE_FORBIDDEN`**; the page never appends a guest message and opens `progressive-auth-modal` | — |
| `GET /api/v1/chat?room_id=chat-{id}` | Chat history (optional) | Skipped on 404/405 |
| `POST /api/v1/auth/login` | Modal sign-in | — |
| `POST /api/v1/cart` `{guest_token, items}` | FR-4.4 merge on login (server sums per variant, caps by stock) | Cart stays staged locally |

Stream URL: `playback_url` from the match detail; co-streams use `http://<host>:8888/costream/{id}/index.m3u8`.

## DOM contract (all 9 present in the initial HTML)

`guest-video-player`, `live-score-banner` (text only, e.g. `1 - 0`), `pinned-merch-card`
(`data-product-id`, `data-variant-id`), `add-to-guest-cart-btn`, `guest-cart-count`, `chat-message-list`,
`chat-input-field`, `chat-send-btn`, `progressive-auth-modal` (hidden until a protected write).

Accessibility: text contrast ≥ 4.5:1 (values in `styles.css`), visible focus ring, every control ≥ 48×48 px,
ARIA labels on all media controls, modal traps focus and closes on Esc, `prefers-reduced-motion` honoured.
