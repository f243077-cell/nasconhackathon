# Live match QR (match-m1)

| File | Encodes | Use |
|---|---|---|
| `match-m1-live-LAN-172.15.58.26.png` | `http://172.15.58.26:8080/q/m1-live` | Scan with a phone on the same Wi-Fi as Tanzeel's laptop |
| `match-m1-live-localhost.png` | `http://localhost:8080/q/m1-live` | Official export (`GET /audit/v1/qr/match-m1/export.png`); works on a phone with `adb reverse tcp:8080 tcp:8080` |
| `match-m1-live-poster.pdf` | same short URL | Printable poster (`export.pdf`) |

The short link answers 302 to `/web/matches/match-m1/live` while the match is `in_progress` (state after `POST /audit/v1/reset`).
If the laptop IP changes, regenerate the LAN file.
