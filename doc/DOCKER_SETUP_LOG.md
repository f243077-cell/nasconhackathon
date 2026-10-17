# NaSCon '26: Docker Image Bundle Setup Log

**Date:** 2026-10-16 (the day before Day 1)
**Machine:** Windows 10 Pro, Intel/AMD (x86_64), Docker Desktop 29.8.1, 4 CPUs, about 10 GB RAM available to Docker
**Source:** `Official_Participant_Rules_Booklet.pdf`, Section 2, "Mandatory Pre-Pulled Docker Bundle"

---

## 1. What was done

1. Read the rules booklet PDF and the screenshot of Section 2.
2. Checked that Docker was running. Server 29.8.1, amd64.
3. Checked disk space. `D:` had 12 GB free and `C:` had 125 GB free.
4. Ran `docker pull` for every image in Section 2:
   - This machine is Intel/AMD Windows, so `selenium/node-edge:4.24.0` was pulled.
   - The Apple Silicon image `seleniarm/node-chromium:4.24.0` was skipped.
   - Both backend runtime images were pulled, `python:3.12-slim` and `node:20-alpine`. The booklet says to pick ONE, but having both lets the team choose on the day.
5. Calculated the "Docker Cache Verification Hash" for the Google Form (page 4).

---

## 2. Pull results

| # | Image | Result |
|---|-------|--------|
| 1 | `postgres:16-alpine` | OK |
| 2 | `redis:7-alpine` | OK |
| 3 | `minio/minio:RELEASE.2024-09-22T00-33-43Z` | **FAILED** |
| 4 | `rabbitmq:3.13-management-alpine` | OK |
| 5 | `nats:2.10-alpine` | OK |
| 6 | `bluenviron/mediamtx:1.9.1` | OK |
| 7 | `livekit/livekit-server:v1.7.2` | OK |
| 8 | `binwiederhier/ntfy:v2.11.0` | OK |
| 9 | `prom/prometheus:v2.54.1` | OK |
| 10 | `grafana/grafana:11.2.0` | OK |
| 11 | `grafana/k6:0.54.0` | OK |
| 12 | `selenium/hub:4.24.0` | OK |
| 13 | `selenium/node-chrome:4.24.0` | OK |
| 14 | `selenium/node-firefox:4.24.0` | OK |
| 15 | `selenium/node-edge:4.24.0` | OK |
| 16 | `python:3.12-slim` (backend option) | OK |
| 17 | `node:20-alpine` (backend option) | OK |
| — | `seleniarm/node-chromium:4.24.0` | Not pulled (Apple Silicon only) |

**Summary:** 16 of 17 images were pulled. Only MinIO failed.

### The MinIO failure

The pull was tried twice. Both times it gave this error:

```
Error response from daemon: pull access denied for minio/minio, repository does not exist or may require 'docker login'
```

`docker manifest inspect minio/minio:latest` also failed. The whole `minio/minio` repository is no longer available on Docker Hub, not only this one tag. This is not a problem with our network or setup.

**Action:** Tell the organisers that this image can't be downloaded.

**Fallback (added later in the session):**

| Image | Result |
|---|---|
| `quay.io/minio/minio` (pinned tag and `latest`) | Not available |
| `bitnami/minio:latest` | Not available |
| **`bitnamilegacy/minio:2024.9.22`** | **Available.** Pulled (amd64, about 389 MB). |

The fallback was smoke-tested with `docker run -e MINIO_ROOT_USER=minioadmin -e MINIO_ROOT_PASSWORD=minioadmin123 -p 19000:9000 bitnamilegacy/minio:2024.9.22`, and `/minio/health/live` returned **200**. `docker-compose.yml` uses this image as the object store (see `AGREED_RULES.md`). This extra image changes the output of the raw form command, but not the recommended hash in Section 3, which was calculated from the image names only.

---

## 3. Docker Cache Verification Hash (Google Form, page 4)

### The form's command

```bash
docker images --format "{{.Repository}}:{{.Tag}}" | sort | sha256sum | cut -c1-16
```

Things to watch out for:
- The form shows `–format` with an en dash. You must type it as `--format` with two hyphens.
- `sha256sum` is not available in PowerShell. Run the command in **Git Bash** or WSL.
- The command hashes **every image on the machine**. This laptop already had about 25 other images (`bioguard-*`, `chaos-shop/*`, `mongo`, `postgres:latest`, `redis:latest`, `nginx`, `busybox` and others). Running the command as written gives a hash that does not match the bundle.

### Calculated hashes

Each hash below was made from the exact list of image names, so other images on the machine don't affect it. The commands used `LC_ALL=C sort` and `sha256sum` in Git Bash.

| Option | Image set | Hash |
|--------|-----------|------|
| **A (submitted / recommended)** | 13 base images + `selenium/node-edge` (no MinIO, no backend). This is 14 images. | **`002b49957e5aa82f`** |
| B | 13 base images + MinIO (no edge, no backend). This is 14 images. | `db84ff4431e450e4` |
| C | Option A + `python:3.12-slim` | `6a75597a0c1e0f32` |
| D | Option A + `node:20-alpine` | `b51ec2e0850a2fa2` |
| E | Command run as written on this machine, including unrelated images | `7d2434608a8b1487` (do not use) |

"13 base images" means rows 1–2 and 4–14 of the pull table: every fixed image except MinIO and Edge.

**Why option A:** The form asks for "the 14 Docker images listed in Section 2". For an Intel/AMD machine, Section 2 lists 15 fixed images, not counting the backend. MinIO can't be downloaded, which leaves exactly 14. **This is an interpretation, not something we confirmed.** We don't know which set the organisers used for their expected hash. If they say otherwise, use B, C or D from the table.

### Getting a clean hash from the real Docker cache (optional)

To make the form's command work as written, the machine must hold only the bundle images. That means deleting every other image. **This cannot be undone.** Your other projects' images would have to be rebuilt or pulled again. Only do this if you really need it:

```bash
# Shows the images that are NOT in the bundle, so you can check before deleting anything
docker images --format "{{.Repository}}:{{.Tag}}" | sort
```

---

## 4. Notes for competition day

- Don't run `docker image prune -a` or `docker system prune -a` before the event. They delete the pulled images, and campus Wi-Fi limits Docker Hub downloads.
- To save RAM, give Selenium browser containers `shm_size: "1gb"` and `SE_START_VNC: "false"` (booklet, Section 3).
- The autograder runs `docker-compose.yml` on GitHub's `ubuntu-latest` runner, which is x86_64 with 16 GB RAM. All the pulled images are amd64, so they match the runner.
