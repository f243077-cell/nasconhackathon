# PlayGrid (Flutter, Android)

Release build: `release/app-release.apk` (arm64-v8a, minSdk 29 / Android 10+).

## Build and install

```
flutter pub get
flutter build apk --release --target-platform android-arm64
adb install -r build/app/outputs/flutter-apk/app-release.apk
```

Server address: Account → Server address (or the server icon on Sign in). Emulator `http://10.0.2.2:8080`,
phone on the same network `http://<api-laptop-ip>:8080`.

If the venue Wi-Fi blocks phone-to-laptop traffic, route the phone over USB instead: run a TCP relay on the
laptop from `127.0.0.1:8080` to the API host, then `adb reverse tcp:8080 tcp:8080` and set the server
address to `http://127.0.0.1:8080`.

## Deep links (Part II §8.4)

```
adb shell am start -W -a android.intent.action.VIEW -d "nascon://entity/match-m1"
adb shell am start -W -a android.intent.action.VIEW -d "nascon://stream/cs-session-101"
```

Both open without a login stop (read-only guest mode when signed out): Match Live and Co-Stream. Measured cold
start on a physical Android 15 phone: 560–860 ms. `nascon://entity/club-*` opens the club page.

## Screens added for Part II

| Screen | Route | Notes |
|---|---|---|
| Match Live | `/live/{match_id}` | Score from `/ws/matches/{id}` (snapshot, then updates), audit score fallback |
| Co-Stream | `/costream/{session_id}` | Composite HLS link, on-air list, host invite / mute / spotlight / kick / leave, join by token, `chat-{session_id}` room |
| Scan QR | `/scan` | `/q/{code}` short links follow the server's live 302 target; also `nascon://` and `/web/` URLs |
| Go Live | `/broadcast` | Stream key generate / rotate / revoke with RTMP, WHIP and HLS endpoints |

UiAutomator2 locators: Flutter `Semantics(identifier: …)` becomes the view's resource-id, e.g.
`match-live-screen`, `costream-screen`, `chat-input`, `chat-send`, `login-submit`.

## Appium (Part II §6.3)

```
appium --port 4723
set API_BASE=http://127.0.0.1:8080
set ANDROID_UDID=<adb serial>
python -m pytest tests/appium -v --junitxml=tests/reports/appium-report.xml
```

Xiaomi / MIUI: Developer options → enable "Install via USB" (and ideally "USB debugging (Security settings)").
The suite sets `appium:ignoreHiddenApiPolicyError` and the cross-surface test needs no taps, so it runs even when
MIUI blocks input injection.
