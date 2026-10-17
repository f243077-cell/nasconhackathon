import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../core/api_client.dart';
import '../core/errors.dart';
import '../core/secure_store.dart';
import '../core/session.dart';
import 'local_db.dart';
import 'models.dart';
import 'repository.dart';
import 'sync_queue.dart';

/// The real backend (/api/v1, AGREED_RULES §4).
///
/// Reads go to the network first and the response is cached in SQLite; when the server is
/// unreachable (or we already know we are offline) the cached copy is returned, so a screen
/// opened once online still opens in airplane mode. Writes never fall back: offline writes
/// go through the sync queue instead (see SyncController.enqueue).
class ApiRepository implements AppRepository {
  ApiRepository(this.ref);

  final Ref ref;

  bool get _offline => ref.read(syncProvider).isOffline;

  Future<T> _read<T>(String cacheKey, Future<dynamic> Function() fetch, T Function(dynamic json) parse) async {
    if (!_offline) {
      try {
        final data = await fetch();
        await LocalDb.putCache(cacheKey, data);
        return parse(data);
      } on ApiException catch (e) {
        if (e.code != 'OFFLINE') throw _signOutIfExpired(e);
        ref.read(syncProvider.notifier).reportUnreachable();
      }
    }
    final cached = await LocalDb.getCache(cacheKey);
    if (cached == null) throw ApiException('OFFLINE');
    return parse(cached);
  }

  Future<dynamic> _write(String path, Object? body) async {
    if (_offline) throw ApiException('OFFLINE');
    try {
      return await ApiClient.post(path, body);
    } on ApiException catch (e) {
      throw _signOutIfExpired(e);
    }
  }

  /// An expired or rejected token sends the user back to Login (the router redirects on null session).
  ApiException _signOutIfExpired(ApiException e) {
    if (e.code == 'UNAUTHENTICATED' && SecureStore.token != null) ref.read(sessionProvider.notifier).logout();
    return e;
  }

  static List<Map<String, dynamic>> _list(dynamic json) => [for (final x in json as List) Map<String, dynamic>.from(x)];

  @override
  Future<Session> login(String email, String password) async {
    final res = Map<String, dynamic>.from(await ApiClient.post('/api/v1/auth/login', {'email': email, 'password': password}));
    final user = Map<String, dynamic>.from(res['user']);
    final leagueIds = (user['league_ids'] as List?) ?? const [];
    user['league_id'] = leagueIds.isEmpty ? null : leagueIds.first;
    res['user'] = user;
    // Tenant logos come back as server paths ("/static/x.png"): make them absolute.
    final tenant = Map<String, dynamic>.from(res['tenant'] ?? {});
    final logo = tenant['logo_url'];
    if (logo is String && logo.startsWith('/')) tenant['logo_url'] = '${await ApiClient.baseUrl()}$logo';
    res['tenant'] = tenant;
    await SecureStore.saveSession(res);
    return Session.fromJson(res);
  }

  @override
  Future<List<League>> leagues() =>
      _read('leagues', () => ApiClient.get('/api/v1/leagues'), (j) => [for (final l in _list(j)) League.fromJson(l)]);

  @override
  Future<List<Fixture>> fixtures(String leagueId) => _read('fixtures:$leagueId',
      () => ApiClient.get('/api/v1/leagues/$leagueId/fixtures'), (j) => [for (final f in _list(j)) Fixture.fromJson(f)]);

  @override
  Future<MatchDetail> match(String matchId) => _read('match:$matchId', () => ApiClient.get('/api/v1/matches/$matchId'),
      (j) => MatchDetail.fromJson(Map<String, dynamic>.from(j)));

  /// The standings table only carries team ids; names come from the league's fixtures.
  @override
  Future<Standings> standings(String leagueId) async {
    final table = await _read('standings:$leagueId', () => ApiClient.get('/api/v1/standings/$leagueId'),
        (j) => Map<String, dynamic>.from(j));
    final names = <String, String>{};
    try {
      for (final f in await fixtures(leagueId)) {
        names[f.home] = f.homeName;
        names[f.away] = f.awayName;
      }
    } catch (_) {
      // names are cosmetic: fall back to ids
    }
    return Standings.fromJson(table, names);
  }

  @override
  Future<Club> club(String clubId) =>
      _read('club:$clubId', () => ApiClient.get('/api/v1/clubs/$clubId'), (j) => Club.fromJson(Map<String, dynamic>.from(j)));

  @override
  Future<List<Product>> products({String? clubId}) => _read(
      'products:${clubId ?? 'all'}',
      () => ApiClient.get('/api/v1/products', query: {'club_id': ?clubId}),
      (j) => [for (final p in _list(j)) Product.fromJson(p)]);

  @override
  Future<Order> checkout(Map<String, dynamic> body) async =>
      Order.fromJson(Map<String, dynamic>.from(await _write('/api/v1/checkout', body)));

  @override
  Future<Map<String, dynamic>> postEvent(Map<String, dynamic> body) async =>
      Map<String, dynamic>.from(await _write('/api/v1/events', body));

  @override
  Future<Map<String, dynamic>> rosterTransfer(Map<String, dynamic> body) async =>
      Map<String, dynamic>.from(await _write('/api/v1/roster/transfer', body));

  @override
  Future<Map<String, dynamic>> sync(String deviceId, List<Map<String, dynamic>> actions) async =>
      Map<String, dynamic>.from(await ApiClient.post('/api/v1/sync', {'device_id': deviceId, 'actions': actions}));

  @override
  Future<void> pinProduct(String matchId, String productId) =>
      _write('/api/v1/matches/$matchId/pin', {'product_id': productId});

  @override
  Future<void> setMatchStatus(String matchId, String to, {String? reason}) =>
      _write('/api/v1/matches/$matchId/status', {'to': to, 'reason': ?reason});

  @override
  Future<List<EventType>> eventTypes(String sportId) => _read('event_types:$sportId',
      () => ApiClient.get('/api/v1/sports/$sportId/event-types'),
      (j) => [for (final t in _list((j as Map)['event_types'])) EventType.fromJson(t)]);

  @override
  Future<List<Map<String, dynamic>>> squads(String leagueId) => _read('squads:$leagueId',
      () => ApiClient.get('/api/v1/leagues/$leagueId/squads'), (j) => _list((j as Map)['squads']));

  @override
  Future<RosterHistory> rosterHistory(String playerId) => _read('roster_history:$playerId',
      () => ApiClient.get('/api/v1/roster/history/$playerId'), (j) => RosterHistory.fromJson(Map<String, dynamic>.from(j)));

  @override
  Future<List<int>> receiptPdf(String orderId) {
    if (_offline) throw ApiException('OFFLINE');
    return ApiClient.getBytes('/api/v1/orders/$orderId/receipt');
  }

  /// WS /api/v1/ws. Reconnects every 3 s while signed in and online; one socket, never polling.
  @override
  Stream<Map<String, dynamic>> liveUpdates() async* {
    while (true) {
      if (SecureStore.token != null && !_offline) {
        WebSocketChannel? channel;
        try {
          channel = WebSocketChannel.connect(await ApiClient.websocketUri());
          await channel.ready;
          await for (final msg in channel.stream) {
            final decoded = jsonDecode(msg as String);
            if (decoded is Map) yield Map<String, dynamic>.from(decoded);
          }
        } catch (_) {
          // dropped or refused: retry below
        } finally {
          await channel?.sink.close();
        }
      }
      await Future<void>.delayed(const Duration(seconds: 3));
    }
  }
}
