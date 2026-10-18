import 'dart:async';
import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../../core/api_client.dart';
import '../../core/config.dart';
import '../../core/errors.dart';

// Part II live surfaces (FR-3.2, FR-3.3, FR-4.1). Everything here works for a signed-out viewer:
// deep links and QR scans must open Match Live / Co-Stream without stopping at login.

/// Where a nascon:// link, a /q/ short link or a /web/ route should land in the app.
/// `nascon://entity/match-m1`, `nascon://stream/cs-session-101`, and the host-less forms Android
/// can hand over (`/match-m1`, `/entity/match-m1`) all resolve here.
String? appRouteForEntity(String id) {
  if (id.startsWith('cs-session-')) return '/costream/$id';
  if (id.startsWith('match-')) return '/live/$id';
  if (id.startsWith('club-')) return '/club/$id';
  if (id.startsWith('player-')) return '/fixtures';
  return null;
}

String? appRouteForUri(Uri uri) {
  final segs = uri.pathSegments.where((s) => s.isNotEmpty).toList();
  if (uri.scheme == 'nascon') {
    if (uri.host == 'stream' && segs.isNotEmpty) return '/costream/${segs.last}';
    if (uri.host == 'entity' && segs.isNotEmpty) return appRouteForEntity(segs.last);
  }
  // Host-less delivery: "/entity/match-m1", "/stream/cs-session-101" or just "/match-m1".
  if (segs.length == 2 && segs.first == 'stream') return '/costream/${segs.last}';
  if (segs.length == 2 && segs.first == 'entity') return appRouteForEntity(segs.last);
  if (segs.length == 1) return appRouteForEntity(segs.single);
  // Guest web routes (from a /q/ redirect): /web/matches/{id}/live, /web/costream/{id}, /web/clubs/{id}
  if (segs.length >= 3 && segs.first == 'web') return appRouteForEntity(segs[2]);
  return null;
}

/// QR payload -> app route. Accepts nascon:// links, /web/ URLs and /q/{code} short links
/// (resolved by asking the server where the short link points right now).
Future<String?> resolveScannedCode(String raw) async {
  final uri = Uri.tryParse(raw.trim());
  if (uri == null) return null;
  final direct = appRouteForUri(uri);
  if (direct != null) return direct;
  final segs = uri.pathSegments.where((x) => x.isNotEmpty).toList();
  if (segs.length == 2 && segs.first == 'q') {
    // Printed codes carry the canonical short URL (http://localhost:8080/q/...); always resolve the short code
    // against the server this phone is configured for, with a timeout so a bad network can't hang the scanner.
    final base = await ServerConfig.load();
    final url = '$base/q/${segs[1]}';
    try {
      final res = await Dio(BaseOptions(connectTimeout: const Duration(seconds: 6), receiveTimeout: const Duration(seconds: 6)))
          .get(url, options: Options(followRedirects: false, validateStatus: (s) => s != null && s < 500, responseType: ResponseType.plain));
      if (res.statusCode == 404) throw ApiException('QR_NOT_FOUND');
      final location = res.headers.value('location');
      if (location != null) return appRouteForUri(Uri.parse(location));
    } on DioException {
      throw ApiException('OFFLINE');
    }
  }
  return null;
}

// ---------------------------------------------------------------- live score

class LiveScore {
  final String status;
  final num home;
  final num away;
  final String? homeId;
  final String? awayId;
  const LiveScore({required this.status, required this.home, required this.away, this.homeId, this.awayId});

  LiveScore merge(Map<String, dynamic> m) {
    final d = m['data'] is Map ? {...m, ...Map<String, dynamic>.from(m['data'])} : m;
    num? pick(String side) {
      final s = d[side];
      if (s is Map && s['score'] != null) return s['score'] as num;
      return d['${side}_score'] as num?;
    }

    String? team(String side) => d[side] is Map ? (d[side]['team_id'] as String?) : null;
    return LiveScore(
      status: (d['status'] as String?) ?? status,
      home: pick('home') ?? home,
      away: pick('away') ?? away,
      homeId: team('home') ?? homeId,
      awayId: team('away') ?? awayId,
    );
  }

}

/// Score for one match, open to guests: the Day 1 audit read for the first paint, then the
/// /ws/matches/{id} feed (snapshot first, then every update). Messages without a score trigger a re-read.
final liveScoreProvider = StreamProvider.autoDispose.family<LiveScore, String>((ref, matchId) {
  final controller = StreamController<LiveScore>();
  var current = const LiveScore(status: 'in_progress', home: 0, away: 0);
  WebSocketChannel? channel;
  Timer? retry;
  var closed = false;

  Future<void> reread() async {
    try {
      final res = await ApiClient.get('/audit/v1/score/$matchId', timeout: const Duration(seconds: 4));
      if (res is Map) {
        current = current.merge(Map<String, dynamic>.from(res));
        if (!closed) controller.add(current);
      }
    } on ApiException catch (e) {
      if (!closed && current.homeId == null) controller.addError(e);
    }
  }

  Future<void> connect() async {
    if (closed) return;
    final base = Uri.parse(await ServerConfig.load());
    final uri = base.replace(scheme: base.scheme == 'https' ? 'wss' : 'ws', path: '/ws/matches/$matchId');
    try {
      channel = WebSocketChannel.connect(uri);
      await channel!.ready;
      channel!.stream.listen(
        (raw) {
          try {
            final m = Map<String, dynamic>.from(jsonDecode(raw as String) as Map);
            final d = m['data'] is Map ? Map<String, dynamic>.from(m['data']) : m;
            final carriesScore = d.containsKey('home_score') || d['home'] is Map;
            if (carriesScore) {
              current = current.merge(m);
              controller.add(current);
            } else {
              reread();
            }
          } catch (_) {/* ignore malformed frames */}
        },
        onDone: () => retry = Timer(const Duration(seconds: 2), connect),
        onError: (_) => retry = Timer(const Duration(seconds: 2), connect),
        cancelOnError: true,
      );
    } catch (_) {
      // Feed down: keep the score fresh by re-reading (well inside the rate limit).
      retry = Timer(const Duration(seconds: 2), () async {
        await reread();
        connect();
      });
    }
  }

  reread();
  connect();
  ref.onDispose(() {
    closed = true;
    retry?.cancel();
    channel?.sink.close();
    controller.close();
  });
  return controller.stream;
});

/// Team names and pinned merch when the viewer is signed in (guests see club ids as names).
final liveMatchMetaProvider = FutureProvider.autoDispose.family<Map<String, dynamic>?, String>((ref, matchId) async {
  try {
    final res = await ApiClient.get('/api/v1/matches/$matchId');
    return res is Map ? Map<String, dynamic>.from(res) : null;
  } on ApiException {
    return null;
  }
});

String prettyId(String? id) => (id ?? '')
    .replaceFirst(RegExp(r'^(club|player|match)-'), '')
    .split(RegExp(r'[-_]+'))
    .where((w) => w.isNotEmpty)
    .map((w) => w[0].toUpperCase() + w.substring(1))
    .join(' ');

// ---------------------------------------------------------------- co-stream chat

class ChatMessage {
  final String key;
  final String sender;
  final String text;
  final bool flagged;
  const ChatMessage({required this.key, required this.sender, required this.text, this.flagged = false});

  factory ChatMessage.fromJson(Map<String, dynamic> j) => ChatMessage(
        key: '${j['message_id'] ?? j['seq'] ?? j['sequence'] ?? '${j['sender']}|${j['text']}'}',
        sender: '${j['sender_name'] ?? j['sender'] ?? 'Fan'}',
        text: '${j['text'] ?? ''}',
        flagged: j['flagged'] == true,
      );
}

/// Chat history for `chat-{session}` rooms, refreshed every 2 s (20 req / 10 s budget is far under 100).
final chatProvider = StreamProvider.autoDispose.family<List<ChatMessage>, String>((ref, roomId) {
  final controller = StreamController<List<ChatMessage>>();
  final seen = <String, ChatMessage>{};
  var supported = true;
  Timer? timer;

  Future<void> load() async {
    if (!supported) return;
    try {
      final res = await ApiClient.get('/api/v1/chat', query: {'room_id': roomId});
      final list = res is List ? res : (res is Map ? (res['messages'] as List? ?? const []) : const []);
      for (final m in list) {
        final msg = ChatMessage.fromJson(Map<String, dynamic>.from(m as Map));
        seen[msg.key] = msg;
      }
      controller.add(seen.values.toList());
    } on ApiException catch (e) {
      if (e.code == 'HTTP_404' || e.code == 'HTTP_405') supported = false;
      controller.add(seen.values.toList());
    }
  }

  load();
  timer = Timer.periodic(const Duration(seconds: 2), (_) => load());
  ref.onDispose(() {
    timer?.cancel();
    controller.close();
  });
  return controller.stream;
});

/// POST /api/v1/chat. A guest gets 403 GUEST_WRITE_FORBIDDEN from the server (rethrown for the UI).
Future<ChatMessage?> sendChat(String roomId, String text) async {
  final res = await ApiClient.post('/api/v1/chat', {'room_id': roomId, 'chat_room_id': roomId, 'text': text});
  // Show the server's moderated copy (profanity already ***), never the typed text. A blocked message
  // (flood / rate) comes back delivered:false and is not shown.
  final msg = res is Map ? res['message'] : null;
  if (res is! Map || res['delivered'] == false || msg is! Map) return null;
  return ChatMessage.fromJson({'sender': 'You', ...Map<String, dynamic>.from(msg)});
}

// ---------------------------------------------------------------- broadcaster

class StreamKey {
  final String streamKey;
  final String status; // active | revoked
  final String label;
  final String? rtmp;
  final String? webrtc;
  final String? playback;
  const StreamKey({required this.streamKey, required this.status, required this.label, this.rtmp, this.webrtc, this.playback});

  factory StreamKey.fromJson(Map<String, dynamic> j) {
    final ingest = j['ingest_endpoints'] is Map ? Map<String, dynamic>.from(j['ingest_endpoints']) : const <String, dynamic>{};
    return StreamKey(
      streamKey: '${j['stream_key'] ?? ''}',
      status: '${j['status'] ?? 'active'}',
      label: '${j['label'] ?? 'default'}',
      rtmp: ingest['rtmp'] as String?,
      webrtc: ingest['webrtc'] as String?,
      playback: j['playback_url'] as String?,
    );
  }
}

/// generate | rotate | revoke. Uses the member route (own player only); falls back to the audit
/// contract route while the member wrapper isn't deployed.
Future<StreamKey> streamKeyAction(String action, String playerId, {String label = 'Mobile'}) async {
  final body = {'action': action, 'player_id': playerId, 'label': label};
  try {
    final res = await ApiClient.post('/api/v1/stream/key', body);
    return StreamKey.fromJson(Map<String, dynamic>.from(res as Map));
  } on ApiException catch (e) {
    if (e.code != 'HTTP_404' && e.code != 'HTTP_405') rethrow;
    final res = await ApiClient.post('/audit/v1/stream/key', body);
    return StreamKey.fromJson(Map<String, dynamic>.from(res as Map));
  }
}

// ---------------------------------------------------------------- co-stream session + host controls (FR-3.3)

class CoStreamSession {
  final String sessionId;
  final String status; // active | terminated
  final String? host;
  final List<String> participants;
  final List<String> muted;
  final String? spotlight;
  final String layout;
  final String? playbackUrl;
  final String chatRoomId;
  const CoStreamSession({
    required this.sessionId,
    required this.status,
    required this.host,
    required this.participants,
    required this.muted,
    required this.spotlight,
    required this.layout,
    required this.playbackUrl,
    required this.chatRoomId,
  });

  factory CoStreamSession.fromJson(Map<String, dynamic> j) => CoStreamSession(
        sessionId: '${j['session_id']}',
        status: '${j['status'] ?? 'active'}',
        host: j['active_host'] as String?,
        participants: [for (final p in (j['active_participants'] as List? ?? const [])) '$p'],
        muted: [for (final p in (j['muted'] as List? ?? const [])) '$p'],
        spotlight: j['spotlight'] as String?,
        layout: '${j['layout'] ?? 'grid_4'}',
        playbackUrl: j['composite_playback_url'] as String?,
        chatRoomId: '${j['chat_room_id'] ?? 'chat-${j['session_id']}'}',
      );
}

/// Live view of a co-stream (guests can read it). Refreshed every 3 s so a host handoff shows up quickly.
final coStreamProvider = StreamProvider.autoDispose.family<CoStreamSession?, String>((ref, sessionId) {
  final controller = StreamController<CoStreamSession?>();
  Timer? timer;
  Future<void> load() async {
    try {
      final res = await ApiClient.get('/api/v1/costream/sessions/$sessionId');
      controller.add(res is Map ? CoStreamSession.fromJson(Map<String, dynamic>.from(res)) : null);
    } on ApiException catch (e) {
      if (e.code == 'STREAM_NOT_FOUND' || e.code == 'HTTP_404') {
        controller.add(null);
      } else if (!controller.isClosed) {
        controller.addError(e);
      }
    }
  }

  load();
  timer = Timer.periodic(const Duration(seconds: 3), (_) => load());
  ref.onDispose(() {
    timer?.cancel();
    controller.close();
  });
  return controller.stream;
});

/// Host / participant actions. Each returns the updated session view when the server sends one.
class CoStreamApi {
  static String _p(String id) => '/api/v1/costream/sessions/$id';

  static Future<String?> invite(String sessionId, String playerId) async {
    final res = await ApiClient.post('${_p(sessionId)}/invite', {'player_id': playerId});
    return res is Map ? res['invite_token'] as String? : null;
  }

  static Future<void> join(String sessionId, String inviteToken) =>
      ApiClient.post('${_p(sessionId)}/join', {'invite_token': inviteToken});

  static Future<void> mute(String sessionId, String playerId, {required bool muted}) =>
      ApiClient.post('${_p(sessionId)}/mute', {'player_id': playerId, 'muted': muted});

  static Future<void> spotlight(String sessionId, String playerId) =>
      ApiClient.post('${_p(sessionId)}/spotlight', {'player_id': playerId});

  static Future<void> kick(String sessionId, String playerId) =>
      ApiClient.post('${_p(sessionId)}/kick', {'player_id': playerId});

  static Future<void> leave(String sessionId) => ApiClient.post('${_p(sessionId)}/leave', const <String, dynamic>{});
}
