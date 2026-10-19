/* Guest Web Player (FR-4.2 / FR-4.3 / FR-4.4, NFR-8). No framework, no CDN (hls.js is vendored).
 *
 * Routes (all served the same index.html by routes/web.py):
 *   /web/matches/{id}/live | preview | vod | notice?state=…   /web/costream/{id}
 *   /web/players/{id}   /web/clubs/{id}
 *
 * Rules this file keeps:
 *  - No login wall: the page renders and plays as a guest. The auth modal opens ONLY on a protected
 *    write (chat send, checkout).
 *  - A guest chat send is never appended locally; the server answers 403 GUEST_WRITE_FORBIDDEN and the
 *    progressive-auth-modal opens with the staged cart kept.
 *  - The score banner updates without reload: WebSocket -> SSE -> polling, whichever works first.
 */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const API = location.origin;
  const MEDIA_HLS = `${location.protocol}//${location.hostname}:8888`;
  const PINNED_DEFAULT = { product_id: "prod-jersey-001", variant_id: "var-jersey-001-L", name: "Home Jersey", label: "Size L", price_minor: 450000 };

  // ---------- route ----------
  const parts = location.pathname.replace(/\/+$/, "").split("/").filter(Boolean); // ["web","matches","match-m1","live"]
  const kind = parts[1] || "matches";
  const entityId = decodeURIComponent(parts[2] || "match-m1");
  const mode = kind === "matches" ? (parts[3] || "live") : kind; // live | preview | vod | notice | costream | players | clubs
  const isCostream = kind === "costream";
  const chatRoom = isCostream ? `chat-${entityId}` : `chat-${entityId}`;

  // ---------- small helpers ----------
  const store = {
    get(k, d = null) { try { const v = sessionStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { sessionStorage.setItem(k, JSON.stringify(v)); } catch { /* private mode: keep in memory */ } },
  };
  const money = (minor) => `PKR ${Math.round(minor / 100).toLocaleString("en-US")}`;
  const titleCase = (id) => String(id || "").replace(/^(club|player|match)-/, "").replace(/[-_]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  const initials = (name) => String(name || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("") || "?";
  const crestColors = (id) => {
    const pairs = [["#2c5bd6", "#102a6b"], ["#d33a2c", "#6e1610"], ["#1f9d55", "#0b4a26"], ["#7c3aed", "#3b1580"], ["#e07a12", "#6e3606"], ["#0f8c86", "#064541"]];
    let h = 7; for (const c of String(id)) h = (h * 31 + c.charCodeAt(0)) >>> 0;
    return pairs[h % pairs.length];
  };
  let toastTimer;
  const toast = (text) => {
    const t = $("toast"); t.textContent = text; t.hidden = false;
    clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, 3200);
  };

  async function http(method, path, { body, token, timeout = 6000 } = {}) {
    const ctrl = new AbortController(); const timer = setTimeout(() => ctrl.abort(), timeout);
    try {
      const headers = { Accept: "application/json" };
      if (body !== undefined) headers["Content-Type"] = "application/json";
      if (token) headers.Authorization = `Bearer ${token}`;
      const res = await fetch(API + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body), signal: ctrl.signal });
      let data = null; try { data = await res.json(); } catch { /* empty or non-JSON body */ }
      return { ok: res.ok, status: res.status, data };
    } catch {
      return { ok: false, status: 0, data: null }; // offline / timeout
    } finally { clearTimeout(timer); }
  }

  // ---------- identity: guest token, member token ----------
  let memberToken = store.get("nascon.member_token");
  let guestToken = store.get("nascon.guest_token");

  async function ensureGuestToken() {
    // FR-4.2: guest tokens are short-lived; fetch a new one once the stored one has expired.
    const exp = store.get("nascon.guest_token_exp");
    if (guestToken && !(exp && Date.parse(exp) <= Date.now())) return guestToken;
    const r = await http("POST", "/api/v1/guest/token", { body: { entity_id: entityId } });
    const tok = r.ok && r.data && (r.data.guest_token || r.data.token);
    if (tok) { guestToken = tok; store.set("nascon.guest_token", tok); store.set("nascon.guest_token_exp", r.data.expires_at || null); }
    return guestToken;
  }
  const readToken = () => memberToken || guestToken;

  // ---------- guest cart (staged locally until sign-in) ----------
  let cart = store.get("nascon.guest_cart", []); // [{variant_id, quantity}]
  const cartCount = () => cart.reduce((n, i) => n + (i.quantity || 0), 0);
  function renderCart() {
    const n = cartCount();
    $("guest-cart-count").textContent = String(n);
    $("auth-cart-count").textContent = String(n);
    $("cart-btn").setAttribute("aria-label", `Guest cart, ${n} item${n === 1 ? "" : "s"}`);
  }
  function addToCart(variantId) {
    const line = cart.find((i) => i.variant_id === variantId);
    if (line) line.quantity = Math.min(10, line.quantity + 1); else cart.push({ variant_id: variantId, quantity: 1 });
    store.set("nascon.guest_cart", cart);
    renderCart();
  }

  // ---------- score ----------
  let lastScore = null;
  let matchStatus = null;

  function setTeams(home, away) {
    for (const [side, team] of [["home", home], ["away", away]]) {
      if (!team) continue;
      const name = team.name || titleCase(team.team_id);
      $(`${side}-name`).textContent = name;
      $(`ov-${side}`).textContent = initials(name).slice(0, 3);
      const crest = $(`${side}-crest`);
      const [c1, c2] = crestColors(team.team_id || name);
      crest.textContent = initials(name);
      crest.style.setProperty("--c1", c1); crest.style.setProperty("--c2", c2);
    }
    if (home && away) {
      const h = home.name || titleCase(home.team_id), a = away.name || titleCase(away.team_id);
      $("match-title").textContent = `${h} versus ${a}`;
      document.title = `${h} vs ${a} | PlayGrid`;
    }
  }

  function setScore(home, away) {
    const text = `${home} - ${away}`;
    const banner = $("live-score-banner");
    if (text !== lastScore) {
      banner.textContent = text;
      $("ov-score").textContent = text;
      banner.setAttribute("aria-label", `Score ${home} to ${away}`);
      if (lastScore !== null) { banner.classList.remove("bump"); void banner.offsetWidth; banner.classList.add("bump"); }
      lastScore = text;
    }
  }

  function setState(status) {
    matchStatus = status;
    const el = $("match-state"), txt = $("match-state-text"), tag = $("live-tag");
    el.classList.remove("upcoming", "done");
    const map = { in_progress: "LIVE", upcoming: "UPCOMING", completed: "FULL TIME", postponed: "POSTPONED", cancelled: "CANCELLED", abandoned: "ABANDONED" };
    txt.textContent = map[status] || (status ? String(status).toUpperCase() : "LIVE");
    if (status && status !== "in_progress") el.classList.add(status === "upcoming" ? "upcoming" : "done");
    tag.hidden = !(status === "in_progress" || isCostream);
  }

  // Accepts the audit score shape {home:{score}, away:{score}, status}, the app shape, or flat home_score/away_score.
  function applyScorePayload(d) {
    if (!d || typeof d !== "object") return false;
    const src = d.data && typeof d.data === "object" ? { ...d, ...d.data } : d;
    const hs = src.home && src.home.score !== undefined ? src.home.score : src.home_score;
    const as = src.away && src.away.score !== undefined ? src.away.score : src.away_score;
    if (src.status) setState(src.status);
    if (src.home && src.away && (src.home.team_id || src.home.name)) setTeams(src.home, src.away);
    if (hs === undefined || as === undefined) return false;
    setScore(hs, as);
    return true;
  }

  async function refreshScore() {
    if (isCostream) return;
    const r = await http("GET", `/audit/v1/score/${encodeURIComponent(entityId)}`);
    if (r.ok) applyScorePayload(r.data);
  }

  async function loadMatchDetail() {
    if (isCostream) return null;
    const token = readToken();
    const r = await http("GET", `/api/v1/matches/${encodeURIComponent(entityId)}`, { token });
    if (!r.ok || !r.data) return null;
    applyScorePayload(r.data);
    if (r.data.league_name) $("match-kicker").textContent = r.data.league_name;
    if (r.data.venue || r.data.scheduled_at) {
      const when = r.data.scheduled_at ? new Date(r.data.scheduled_at).toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit" }) : "";
      $("match-meta").textContent = [r.data.venue, when].filter(Boolean).join(", ");
    }
    if (r.data.pinned_product) renderPinned(r.data.pinned_product);
    return r.data;
  }

  // Live updates: WebSocket first, then SSE, then a polite poll (well under 100 req / 10 s).
  function connectLive() {
    if (isCostream) return connectCostream();
    let fellBack = false;
    const fallbackToSse = () => {
      if (fellBack) return; fellBack = true;
      if (!("EventSource" in window)) return startPolling();
      const es = new EventSource(`${API}/api/v1/matches/${encodeURIComponent(entityId)}/stream${guestToken ? `?guest_token=${encodeURIComponent(guestToken)}` : ""}`);
      let opened = false;
      es.onopen = () => { opened = true; };
      es.onmessage = (e) => onLiveMessage(e.data);
      es.onerror = () => { if (!opened) { es.close(); startPolling(); } };
    };
    try {
      const wsUrl = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/matches/${encodeURIComponent(entityId)}`;
      const ws = new WebSocket(wsUrl);
      let opened = false;
      ws.onopen = () => { opened = true; };
      ws.onmessage = (e) => onLiveMessage(e.data);
      ws.onerror = () => { if (!opened) fallbackToSse(); };
      ws.onclose = () => { if (!opened) fallbackToSse(); else setTimeout(connectLive, 1500); };
    } catch { fallbackToSse(); }
  }
  // Co-stream pages: one read-only socket carries the room's chat (chat-{id}) and session updates (FR-3.3).
  // If sockets are unavailable, poll the chat history once a second; appendChat drops duplicates.
  let chatPolling = false;
  function connectCostream() {
    try {
      const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/costream/${encodeURIComponent(entityId)}`);
      let opened = false;
      ws.onopen = () => { opened = true; };
      ws.onmessage = (e) => onLiveMessage(e.data);
      ws.onclose = () => { if (opened) setTimeout(connectCostream, 1500); else startChatPolling(); };
    } catch { startChatPolling(); }
  }
  function startChatPolling() {
    if (chatPolling) return; chatPolling = true;
    setInterval(loadChat, 1000);
  }
  let polling = false;
  function startPolling() {
    if (polling) return; polling = true;
    setInterval(refreshScore, 400); // /audit/v1/* is exempt from the rate limiter; keeps updates under 500 ms
  }
  function onLiveMessage(raw) {
    let msg; try { msg = JSON.parse(raw); } catch { return; }
    if (msg.type === "chat_message" || msg.type === "chat") { appendChat(msg.data || msg); return; }
    if (msg.type === "product_pinned" && msg.data && msg.data.product) { renderPinned(msg.data.product); return; }
    if (isCostream) return; // costream_snapshot / costream_update carry no match score
    // Score update: use the payload if it carries the score, otherwise refetch (Day 1 messages carry only the event).
    if (!applyScorePayload(msg)) refreshScore();
  }

  // ---------- video ----------
  const video = $("video");
  let hls = null;
  // Low latency first: WebRTC (WHEP) from MediaMTX, < 0.5 s glass-to-glass. HLS is the fallback while no
  // publisher is live; WHEP is retried every 4 s so a host's camera appears without a reload.
  const whepUrlFor = (hlsUrl) => hlsUrl.replace(/:8888\//, ":8889/").replace(/\/index\.m3u8$/, "/whep");
  let pc = null;
  let whepRetry = null;
  async function playWhep(url) {
    const conn = new RTCPeerConnection({ iceServers: [] });
    conn.addTransceiver("video", { direction: "recvonly" });
    conn.addTransceiver("audio", { direction: "recvonly" });
    const stream = new MediaStream();
    conn.ontrack = (e) => {
      stream.addTrack(e.track);
      if (video.srcObject !== stream) {
        if (hls) { hls.destroy(); hls = null; }
        video.removeAttribute("src");
        video.srcObject = stream;
        video.play().catch(() => {});
      }
      $("player-empty").hidden = true;
    };
    conn.onconnectionstatechange = () => {
      if (["failed", "disconnected", "closed"].includes(conn.connectionState) && pc === conn) {
        pc = null; scheduleWhep(url);
      }
    };
    await conn.setLocalDescription(await conn.createOffer());
    await new Promise((res) => {           // gather candidates (non-trickle), at most 1.5 s
      if (conn.iceGatheringState === "complete") return res();
      const t = setTimeout(res, 1500);
      conn.onicegatheringstatechange = () => { if (conn.iceGatheringState === "complete") { clearTimeout(t); res(); } };
    });
    const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/sdp" }, body: conn.localDescription.sdp });
    if (!res.ok) { conn.close(); throw new Error(`WHEP ${res.status}`); }
    await conn.setRemoteDescription({ type: "answer", sdp: await res.text() });
    if (pc) pc.close();
    pc = conn;
  }
  function scheduleWhep(url) {
    clearTimeout(whepRetry);
    whepRetry = setTimeout(() => playWhep(url).catch(() => scheduleWhep(url)), 4000);
  }

  function playStream(url) {
    if (!url) return;
    if (window.RTCPeerConnection && /:8888\/.+\/index\.m3u8$/.test(url)) {
      const whep = whepUrlFor(url);
      const fallback = () => { if (!video.srcObject) { if (pc) { pc.close(); pc = null; } if (!hls && !video.src) playHls(url); } scheduleWhep(whep); };
      // Signalling can succeed while the media path is blocked (UDP/TCP 8189 on venue Wi-Fi): if no track
      // arrives within 5 s, play HLS so the viewer always sees video, and keep retrying WebRTC.
      playWhep(whep).then(() => setTimeout(() => { if (!video.srcObject) fallback(); }, 5000)).catch(fallback);
      return;
    }
    playHls(url);
  }

  function playHls(url) {
    const empty = $("player-empty");
    const ready = () => { empty.hidden = true; };
    if (video.canPlayType("application/vnd.apple.mpegurl")) {
      video.src = url; video.addEventListener("loadeddata", ready, { once: true });
    } else if (window.Hls && window.Hls.isSupported()) {
      hls = new window.Hls({ lowLatencyMode: true, liveSyncDurationCount: 2 });
      hls.loadSource(url); hls.attachMedia(video);
      hls.on(window.Hls.Events.MANIFEST_PARSED, () => { ready(); video.play().catch(() => {}); });
      hls.on(window.Hls.Events.ERROR, (_e, data) => {
        if (data && data.fatal) { $("player-empty-text").textContent = "The broadcast hasn't started yet. The score updates live."; empty.hidden = false; }
      });
    }
  }
  function streamUrlFor(detail) {
    if (isCostream) return `${MEDIA_HLS}/costream/${encodeURIComponent(entityId)}/index.m3u8`;
    if (!detail) return null;
    return detail.playback_url || (detail.stream && detail.stream.playback_url) || detail.vod_url || null;
  }
  function wireControls() {
    const play = $("btn-play"), mute = $("btn-mute"), full = $("btn-full");
    const syncPlay = () => {
      const paused = video.paused;
      play.setAttribute("aria-label", paused ? "Play video" : "Pause video");
      $("icon-play").setAttribute("d", paused ? "M8 5v14l11-7z" : "M6 5h4v14H6zm8 0h4v14h-4z");
    };
    play.addEventListener("click", () => { if (video.paused) video.play().catch(() => {}); else video.pause(); });
    video.addEventListener("play", syncPlay); video.addEventListener("pause", syncPlay);
    mute.addEventListener("click", () => {
      video.muted = !video.muted;
      mute.setAttribute("aria-pressed", String(video.muted));
      mute.setAttribute("aria-label", video.muted ? "Unmute video" : "Mute video");
      $("icon-mute").setAttribute("d", video.muted
        ? "M4 9v6h4l5 5V4L8 9H4Zm12.6 3 2.7-2.7-1.4-1.4L15.2 10.6 12.5 7.9l-1.4 1.4 2.7 2.7-2.7 2.7 1.4 1.4 2.7-2.7 2.7 2.7 1.4-1.4L16.6 12Z"
        : "M4 9v6h4l5 5V4L8 9H4Zm11.5 3A4.5 4.5 0 0 0 13 8v8a4.5 4.5 0 0 0 2.5-4ZM13 3.2v2.1a7 7 0 0 1 0 13.4v2.1a9 9 0 0 0 0-17.6Z");
    });
    full.addEventListener("click", () => {
      const el = $("guest-video-player");
      if (document.fullscreenElement) document.exitFullscreen(); else if (el.requestFullscreen) el.requestFullscreen();
    });
    syncPlay();
  }

  // ---------- pinned merch ----------
  let pinned = { ...PINNED_DEFAULT };
  function renderPinned(product) {
    const variants = Array.isArray(product.variants) ? product.variants : [];
    const v = variants.find((x) => x.variant_id === "var-jersey-001-L") || variants.find((x) => (x.stock ?? 1) > 0) || variants[0];
    pinned = {
      product_id: product.product_id || PINNED_DEFAULT.product_id,
      variant_id: (v && v.variant_id) || PINNED_DEFAULT.variant_id,
      name: product.name || PINNED_DEFAULT.name,
      label: v ? [v.size && `Size ${v.size}`, v.color].filter(Boolean).join(", ") : PINNED_DEFAULT.label,
      price_minor: (v && v.price_minor) || PINNED_DEFAULT.price_minor,
    };
    const card = $("pinned-merch-card");
    card.dataset.productId = pinned.product_id; card.dataset.variantId = pinned.variant_id;
    $("merch-name").textContent = pinned.name;
    $("merch-variant").textContent = pinned.label || "One size";
    $("merch-price").textContent = money(pinned.price_minor);
  }

  // ---------- chat ----------
  const chatList = $("chat-message-list");
  const seen = new Set();
  function appendChat(m) {
    if (!m || !m.text) return;
    const key = m.message_id || m.seq || m.sequence || `${m.sender}|${m.text}|${m.sent_at || ""}`;
    if (seen.has(key)) return; seen.add(key);
    $("chat-empty").hidden = true;
    const li = document.createElement("li");
    li.className = "chat-msg" + (m.flagged ? " flagged" : "");
    const who = document.createElement("span"); who.className = "chat-sender"; who.textContent = m.sender_name || m.sender || "Fan";
    const txt = document.createElement("span"); txt.className = "chat-text"; txt.textContent = m.text; // server already masked profanity as ***
    li.append(who, txt);
    const atBottom = chatList.scrollHeight - chatList.scrollTop - chatList.clientHeight < 40;
    chatList.appendChild(li);
    if (atBottom) chatList.scrollTop = chatList.scrollHeight;
  }
  let chatHistoryWorks = true;
  async function loadChat() {
    if (!chatHistoryWorks) return;
    const r = await http("GET", `/api/v1/chat?room_id=${encodeURIComponent(chatRoom)}`, { token: readToken() });
    if (r.status === 404 || r.status === 405) { chatHistoryWorks = false; return; }
    const items = r.ok && r.data ? (Array.isArray(r.data) ? r.data : r.data.messages || []) : [];
    items.forEach(appendChat);
  }

  async function sendChat(text) {
    const btn = $("chat-send-btn");
    btn.disabled = true;
    try {
      if (!memberToken) {
        // Guest: try the write so the server enforces the boundary; never append the message ourselves.
        await ensureGuestToken();
        await http("POST", "/api/v1/chat", { body: { room_id: chatRoom, chat_room_id: chatRoom, text }, token: guestToken });
        openAuth("chat");
        return;
      }
      const r = await http("POST", "/api/v1/chat", { body: { room_id: chatRoom, chat_room_id: chatRoom, text }, token: memberToken });
      if (r.ok) {
        $("chat-input-field").value = "";
        // Show the server's moderated copy (profanity already ***), never the typed text.
        const d = r.data || {};
        if (d.delivered === false) toast("Message blocked: please don't spam or repeat characters.");
        else if (d.message) appendChat({ sender: "You", ...d.message });
      } else if (r.status === 401 || r.status === 403) {
        memberToken = null; store.set("nascon.member_token", null); openAuth("chat");
      } else if (r.status === 429) {
        toast("Slow down a little. Try again in a moment.");
      } else {
        toast("Message not sent. Check your connection and try again.");
      }
    } finally { btn.disabled = false; }
  }

  // ---------- progressive auth modal ----------
  let lastFocus = null;
  let resumeAt = 0;
  function openAuth() {
    resumeAt = video.currentTime || 0;
    lastFocus = document.activeElement;
    renderCart();
    $("auth-error").textContent = "";
    $("modal-backdrop").hidden = false;
    $("progressive-auth-modal").hidden = false;
    setTimeout(() => $("auth-email").focus(), 0);
  }
  function closeAuth() {
    $("modal-backdrop").hidden = true;
    $("progressive-auth-modal").hidden = true;
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }
  function trapFocus(e) {
    const modal = $("progressive-auth-modal");
    if (modal.hidden) return;
    if (e.key === "Escape") { e.preventDefault(); closeAuth(); return; }
    if (e.key !== "Tab") return;
    const f = [...modal.querySelectorAll("button, input")].filter((el) => !el.disabled && el.offsetParent !== null);
    if (!f.length) return;
    const first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }

  async function signIn(e) {
    e.preventDefault();
    const email = $("auth-email").value.trim(), password = $("auth-password").value;
    if (!email || !password) { $("auth-error").textContent = "Enter your email and password."; return; }
    const submit = $("auth-submit"); submit.disabled = true; submit.textContent = "Signing in";
    try {
      const r = await http("POST", "/api/v1/auth/login", { body: { email, password } });
      if (!r.ok || !r.data || !r.data.token) {
        $("auth-error").textContent = r.status === 0 ? "Can't reach the server. Try again." : "Email or password is incorrect.";
        return;
      }
      memberToken = r.data.token; store.set("nascon.member_token", memberToken);
      // FR-4.4: merge the staged guest cart into the member cart (server sums per variant, capped by stock).
      if (cart.length) {
        const m = await http("POST", "/api/v1/cart", { body: { guest_token: guestToken, items: cart, guest_cart: cart }, token: memberToken });
        if (m.ok) {
          const merged = (m.data && (m.data.active_cart || m.data)) || null;
          cart = merged && Array.isArray(merged.items) ? merged.items.map((i) => ({ variant_id: i.variant_id, quantity: i.quantity })) : cart;
          store.set("nascon.guest_cart", cart);
        }
      }
      guestToken = null; store.set("nascon.guest_token", null); // the guest token is spent after merge
      $("guest-pill").textContent = `Signed in as ${(r.data.user && r.data.user.display_name) || email}`;
      renderCart();
      closeAuth();
      if (resumeAt && Math.abs((video.currentTime || 0) - resumeAt) > 1) { try { video.currentTime = resumeAt; } catch { /* live edge */ } }
      toast("Signed in. You can chat now.");
    } finally { submit.disabled = false; submit.textContent = "Sign In"; }
  }

  // ---------- profile pages (players / clubs) ----------
  async function renderProfile() {
    $("live-view").hidden = true;
    const view = $("profile-view"); view.hidden = false;
    const isPlayer = kind === "players";
    await ensureGuestToken();
    const r = await http("GET", isPlayer ? `/api/v1/athletes/${encodeURIComponent(entityId)}` : `/api/v1/clubs/${encodeURIComponent(entityId)}`, { token: readToken() });
    const d = (r.ok && r.data) || {};
    const name = d.name || d.display_name || titleCase(entityId);
    document.title = `${name} | PlayGrid`;
    const [c1, c2] = crestColors(entityId);
    const rows = (title, list, left, right) => list && list.length
      ? `<section class="card"><h2>${title}</h2><ul>${list.map((x) => `<li><span>${esc(left(x))}</span><span>${esc(right(x))}</span></li>`).join("")}</ul></section>` : "";
    view.innerHTML = `
      <div class="profile-head">
        <span class="crest" style="--c1:${c1};--c2:${c2}" aria-hidden="true">${esc(initials(name))}</span>
        <div><h1>${esc(name)}</h1><p>${esc(isPlayer ? [d.position, d.club_name || (d.clubs && d.clubs[0] && d.clubs[0].name)].filter(Boolean).join(", ") : (d.venue && d.venue.name) || "")}</p>
        ${isPlayer && d.follower_count !== undefined ? `<p>${esc(d.follower_count)} followers</p>` : ""}</div>
      </div>
      ${isPlayer ? rows("Upcoming fixtures", d.upcoming_fixtures, (x) => `${x.home_name || x.home} vs ${x.away_name || x.away}`, (x) => x.scheduled_at ? new Date(x.scheduled_at).toLocaleDateString() : "") : ""}
      ${isPlayer ? rows("Career", d.career || d.career_records, (x) => x.season || x.league_id || "", (x) => `${x.played ?? 0} played`) : ""}
      ${isPlayer ? rows("Watch again", d.vods, (x) => x.title || x.match_id || "VOD", () => "Replay") : ""}
      ${!isPlayer ? rows("Squad", d.roster, (x) => x.name, (x) => x.position || "") : ""}
      ${!isPlayer ? rows("Staff", d.staff, (x) => x.name, (x) => x.role || "") : ""}
      ${!r.ok ? `<section class="card"><p>We couldn't load the full profile right now. Pull to refresh or try again shortly.</p></section>` : ""}`;
  }
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // ---------- boot ----------
  function bindUi() {
    $("add-to-guest-cart-btn").addEventListener("click", () => {
      addToCart(pinned.variant_id);
      toast(`${pinned.name} added to your cart.`);
    });
    $("cart-btn").addEventListener("click", () => {
      if (cartCount() === 0) { toast("Your cart is empty."); return; }
      if (!memberToken) openAuth("checkout"); else toast(`${cartCount()} item(s) in your cart.`);
    });
    $("chat-form").addEventListener("submit", (e) => {
      e.preventDefault();
      const text = $("chat-input-field").value.trim();
      if (!text) { $("chat-input-field").focus(); return; }
      sendChat(text);
    });
    $("auth-form").addEventListener("submit", signIn);
    $("auth-close").addEventListener("click", closeAuth);
    $("auth-later").addEventListener("click", closeAuth);
    $("modal-backdrop").addEventListener("click", closeAuth);
    document.addEventListener("keydown", trapFocus);
  }

  async function bootLive() {
    $("chat-room").textContent = chatRoom;
    if (isCostream) {
      $("match-kicker").textContent = "Co-stream";
      $("match-title").textContent = `Co-stream ${entityId}`;
      $("home-name").textContent = "Live"; $("away-name").textContent = "Co-hosts";
      setState("in_progress");
    } else {
      setState(mode === "preview" ? "upcoming" : mode === "vod" ? "completed" : mode === "notice" ? new URLSearchParams(location.search).get("state") || "postponed" : "in_progress");
      if (mode === "preview") $("player-empty-text").textContent = "Kick-off soon. The stream starts with the match.";
      if (mode === "notice") $("player-empty-text").textContent = `This match is ${new URLSearchParams(location.search).get("state") || "postponed"}. We'll update this page when it's rescheduled.`;
    }
    renderPinned(PINNED_DEFAULT);
    renderCart();
    refreshScore();                 // fast, unauthenticated audit read: score shows immediately
    connectLive();
    await ensureGuestToken();
    const detail = await loadMatchDetail();
    playStream(streamUrlFor(detail));
    loadChat();
  }

  bindUi();
  wireControls();
  if (kind === "players" || kind === "clubs") renderProfile(); else bootLive();
})();
