"""Guest Web Player on Selenium Grid 4 (spec 6.2.3). Run: pytest -n 3 tests/selenium/

1. QR short link -> live page: player + score banner within 3 s, no login modal.
2. Guest chat send is blocked (403) and opens the progressive auth modal; nothing is appended.
3. Add to guest cart -> count 1; a posted score event updates the banner within 500 ms, no reload.
"""
import time
import uuid

import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

LIVE_PATH = "/web/matches/match-m1/live"


def tid(name):
    return By.CSS_SELECTOR, f'[data-testid="{name}"]'


def visible(driver, name, timeout):
    return WebDriverWait(driver, timeout).until(EC.visibility_of_element_located(tid(name)))


def modal_shown(driver):
    return any(el.is_displayed() for el in driver.find_elements(*tid("progressive-auth-modal")))


@pytest.mark.parametrize("driver", ["chrome"], indirect=True)
def test_qr_short_link_opens_live_player_without_login(driver, app_url):
    started = time.monotonic()
    driver.get(f"{app_url}/q/m1-live")
    WebDriverWait(driver, 3).until(EC.url_contains(LIVE_PATH))
    visible(driver, "guest-video-player", 3)
    banner = visible(driver, "live-score-banner", 3)
    assert time.monotonic() - started <= 3.0, "player and score banner must render within 3 s"
    assert driver.current_url.split("?")[0].endswith(LIVE_PATH)
    assert any(ch.isdigit() for ch in banner.text), f"score banner shows no score: {banner.text!r}"
    assert not modal_shown(driver), "a login modal must not open on first load"


@pytest.mark.parametrize("driver", ["firefox"], indirect=True)
def test_guest_chat_send_is_blocked_and_opens_auth_modal(driver, app_url):
    driver.get(f"{app_url}{LIVE_PATH}")
    chat = visible(driver, "chat-message-list", 5)
    before = driver.execute_script("return arguments[0].children.length", chat)
    text = f"guest says hello {uuid.uuid4().hex[:8]}"
    visible(driver, "chat-input-field", 5).send_keys(text)
    visible(driver, "chat-send-btn", 5).click()
    visible(driver, "progressive-auth-modal", 3)
    # give a wrongly accepted message time to show up before checking it did not
    time.sleep(0.5)
    assert driver.execute_script("return arguments[0].children.length", chat) == before
    assert text not in chat.text


# In-browser timing: the page's own fetch posts the event (same origin, no Authorization header, so the
# Day 1 audit route accepts it) and a MutationObserver stamps the banner change. Both clocks are the browser's.
_POST_AND_WATCH = """
const [body, timeoutMs, done] = arguments;
const banner = document.querySelector('[data-testid="live-score-banner"]');
const before = banner.textContent.trim();
let status = null, finished = false, changedAt = null;
const t0 = performance.now();
// The WebSocket update can beat the HTTP response, so finish only once BOTH the status and the change are known.
const finish = (changed) => {
  if (finished) return; finished = true; obs.disconnect();
  done({status, before, after: banner.textContent.trim(), changed,
        elapsed: changed ? changedAt : performance.now() - t0});
};
const tryFinish = () => { if (changedAt !== null && status !== null) finish(true); };
const obs = new MutationObserver(() => {
  if (changedAt === null && banner.textContent.trim() !== before) { changedAt = performance.now() - t0; tryFinish(); }
});
obs.observe(banner, {childList: true, subtree: true, characterData: true});
fetch('/audit/v1/events', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)})
  .then(r => { status = r.status; if (changedAt === null && banner.textContent.trim() !== before) changedAt = performance.now() - t0; tryFinish(); })
  .catch(() => { status = -1; tryFinish(); });
setTimeout(() => finish(changedAt !== null), timeoutMs);
"""


@pytest.mark.parametrize("driver", ["chrome"], indirect=True)
def test_guest_cart_count_and_live_score_update(driver, app_url):
    driver.get(f"{app_url}{LIVE_PATH}")
    count = visible(driver, "guest-cart-count", 5)
    assert count.text.strip() == "0"
    visible(driver, "add-to-guest-cart-btn", 5).click()
    WebDriverWait(driver, 2).until(lambda d: count.text.strip() == "1")
    assert not modal_shown(driver), "adding to the guest cart must not ask for login"

    visible(driver, "live-score-banner", 3)
    url_before = driver.current_url
    event = {"event_id": f"sel-{uuid.uuid4().hex[:12]}", "match_id": "match-m1", "type": "score",
             "payload": {"team_id": "club-alpha-1", "event_type": "goal"}}
    driver.set_script_timeout(10)
    result = driver.execute_async_script(_POST_AND_WATCH, event, 3000)
    assert result["status"] == 201, f"score event not accepted: {result}"
    assert result["changed"], f"banner did not update without reload: {result}"
    assert result["elapsed"] < 500, f"banner updated after {result['elapsed']:.0f} ms (limit 500 ms)"
    assert driver.current_url == url_before, "the page must not reload"
