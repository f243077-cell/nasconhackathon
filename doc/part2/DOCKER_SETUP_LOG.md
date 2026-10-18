# Docker Setup Log (Part II)

**Source:** `App Dev Day 2 Problem Statement.pdf` §1.3, §6.1, §6.2.1 and the Day 1 pull log (`../DOCKER_SETUP_LOG.md`).
**Machine:** Tanzeel's laptop (Windows 10, Intel/AMD x86_64, Docker Desktop).

---

## 1. Images Part II needs

| Service | Spec says | Pulled on Day 1? | Status / action |
|---|---|---|---|
| Media server | MediaMTX / LiveKit / SRS (ports 1935, 8888, 8889) | `bluenviron/mediamtx:1.9.1` ✅, `livekit/livekit-server:v1.7.2` ✅ | **Use MediaMTX 1.9.1** (one container, RTMP + HLS + WebRTC). |
| Selenium hub | `selenium/hub:4.25.0` (compose example) | `selenium/hub:4.24.0` ✅ | **Pull `4.25.0` tonight.** If not possible, use `4.24.0` — graded on `:4444/status` ready with ≥ 3 nodes. |
| Chrome nodes ×2 | `selenium/node-chrome:4.25.0` | `4.24.0` ✅ | Same as above. |
| Firefox node | `selenium/node-firefox:4.25.0` | `4.24.0` ✅ | Same as above. |
| Edge node | not required | `4.24.0` ✅ | Not used (the spec's 3 nodes are chrome, chrome, firefox). |
| k6 | `k6 run tests/k6_load.js` | `grafana/k6:0.54.0` ✅ | Use the image or a local k6 binary. |
| Prometheus / Grafana | `/metrics` only is graded | `prom/prometheus:v2.54.1` ✅, `grafana/grafana:11.2.0` ✅ | Optional for the demo; **not** needed in the graded compose. |
| ntfy | not named in Part II | `binwiederhier/ntfy:v2.11.0` ✅ | Not needed (notifications go over WS/SSE + DLQ). |
| NATS / RabbitMQ | not named | pulled ✅ | Not needed (Redis stays the bus). |
| Postgres, Redis, MinIO, Python | unchanged from Day 1 | ✅ (MinIO via `bitnamilegacy/minio:2024.9.22`) | Unchanged. |
| Appium 2 | port 4723 | — | **Not a Docker image here** — runs on the host with the phone (Node.js `appium` + `uiautomator2`). |

## 2. Commands to run tonight (Tanzeel)

```bash
docker pull selenium/hub:4.25.0
docker pull selenium/node-chrome:4.25.0
docker pull selenium/node-firefox:4.25.0
# already present: bluenviron/mediamtx:1.9.1, grafana/k6:0.54.0
```
Do **not** run `docker system prune -a` or `docker image prune -a`.

## 3. Port check before the sprint
| Port | Owner | Notes |
|---|---|---|
| 8080 | api | Firewall rule `NaSCon_API_8080` already exists (inbound, Private + Public). |
| 1935, 8888, 8889 | mediamtx | Add firewall rules if the phone/OBS on the hotspot must reach them. WebRTC may also need its UDP port. |
| 4444, 4442, 4443 | selenium-hub | Local only (grid + k6 on the same laptop or via `ssh -L`). |
| 4723 | Appium (host) | On the laptop with the phone. |

## 4. RAM note
The grader runner has 8 GB. API (2 workers) + Postgres + Redis + MinIO + MediaMTX + hub + 3 browser nodes (`shm_size: "1gb"` each, `SE_START_VNC=false`) is tight; keep `SE_NODE_MAX_SESSIONS=2` and don't add Grafana/Prometheus to the graded compose.
