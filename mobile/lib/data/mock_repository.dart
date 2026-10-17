import 'dart:async';

import '../core/errors.dart';
import 'models.dart';
import 'repository.dart';

/// In-memory fake backend with the exact /api/v1 JSON shapes, so the UI can be
/// built and demoed before the real API is live. Login with any password:
///   organizer@demo.com, manager@demo.com, player@demo.com, viewer@demo.com, admin@demo.com
class MockRepository implements AppRepository {
  static const _delay = Duration(milliseconds: 400);

  final _live = StreamController<Map<String, dynamic>>.broadcast();

  static const _tenant = {
    'tenant_id': 'ten-1',
    'name': 'Lahore Premier League',
    'logo_url': null,
    'primary_color': '#0B5FFF',
    'secondary_color': '#FFB800',
  };

  static const _users = {
    'admin@demo.com': ('super_admin', 'Ayesha Admin', 'club-1', 'lg-1'),
    'organizer@demo.com': ('league_organizer', 'Omar Organizer', null, 'lg-1'),
    'manager@demo.com': ('club_manager', 'Maria Manager', 'club-1', 'lg-1'),
    'player@demo.com': ('player', 'Pervez Player', 'club-1', 'lg-1'),
    'viewer@demo.com': ('viewer', 'Vera Viewer', null, null),
  };

  final Map<String, String> _teamNames = {
    'club-1': 'Lahore Lions',
    'club-2': 'Karachi Kings',
    'club-3': 'Islamabad Eagles',
    'club-4': 'Multan Sultans',
  };

  late final List<Map<String, dynamic>> _fixtures = [
    _fx('m1', 'club-1', 'club-2', 'in_progress', '2026-10-17T14:00:00Z', 'Gaddafi Stadium'),
    _fx('m2', 'club-3', 'club-4', 'completed', '2026-10-16T16:00:00Z', 'Jinnah Stadium'),
    _fx('m3', 'club-1', 'club-3', 'upcoming', '2026-10-20T15:00:00Z', 'Gaddafi Stadium'),
    _fx('m4', 'club-2', 'club-4', 'upcoming', '2026-10-21T18:30:00Z', 'National Stadium'),
  ];

  Map<String, dynamic> _fx(String id, String h, String a, String status, String at, String venue) => {
        'match_id': id,
        'home': h,
        'away': a,
        'home_name': _teamNames[h],
        'away_name': _teamNames[a],
        'status': status,
        'scheduled_at': at,
        'venue': venue,
      };

  // match_id -> event log. Scores are recomputed from it (like the real backend).
  final Map<String, List<Map<String, dynamic>>> _events = {
    'm1': [
      {'event_id': 'evt-1', 'type': 'match_init', 'payload': {}},
      {'event_id': 'evt-2', 'type': 'match_start', 'payload': {}},
      {'event_id': 'evt-3', 'type': 'score', 'payload': {'team_id': 'club-1', 'event_type': 'goal'}},
      {'event_id': 'evt-4', 'type': 'score', 'payload': {'team_id': 'club-2', 'event_type': 'goal'}},
      {'event_id': 'evt-5', 'type': 'score', 'payload': {'team_id': 'club-1', 'event_type': 'goal'}},
    ],
    'm2': [
      {'event_id': 'evt-6', 'type': 'match_init', 'payload': {}},
      {'event_id': 'evt-7', 'type': 'match_start', 'payload': {}},
      {'event_id': 'evt-8', 'type': 'score', 'payload': {'team_id': 'club-3', 'event_type': 'goal'}},
      {'event_id': 'evt-9', 'type': 'match_end', 'payload': {}},
    ],
    'm3': [
      {'event_id': 'evt-10', 'type': 'match_init', 'payload': {}},
    ],
    'm4': [
      {'event_id': 'evt-11', 'type': 'match_init', 'payload': {}},
    ],
  };

  final Map<String, String> _pinned = {'m1': 'prod-jersey'};

  final List<Map<String, dynamic>> _products = [
    {
      'product_id': 'prod-jersey',
      'name': 'Home Jersey 2026',
      'type': 'apparel',
      'image_url': null,
      'variants': [
        {'variant_id': 'var-jersey-001-S', 'size': 'S', 'color': 'Blue', 'price_minor': 450000, 'stock': 5},
        {'variant_id': 'var-jersey-001-M', 'size': 'M', 'color': 'Blue', 'price_minor': 450000, 'stock': 1},
        {'variant_id': 'var-jersey-001-L', 'size': 'L', 'color': 'Blue', 'price_minor': 450000, 'stock': 0},
      ],
    },
    {
      'product_id': 'prod-scarf',
      'name': 'Supporter Scarf',
      'type': 'accessory',
      'image_url': null,
      'variants': [
        {'variant_id': 'var-scarf-blue', 'size': null, 'color': 'Blue', 'price_minor': 120000, 'stock': 20},
        {'variant_id': 'var-scarf-gold', 'size': null, 'color': 'Gold', 'price_minor': 120000, 'stock': 8},
      ],
    },
    {
      'product_id': 'prod-wallpaper',
      'name': 'Digital Wallpaper Pack',
      'type': 'digital',
      'image_url': null,
      'variants': [
        {'variant_id': 'var-wall-1', 'size': null, 'color': null, 'price_minor': 25000, 'stock': 999},
      ],
    },
  ];

  final Map<String, List<Map<String, dynamic>>> _rosters = {
    'club-1': [
      {'player_id': 'p1', 'name': 'Ali Khan', 'position': 'GK', 'role': 'captain', 'squad_id': 'sq-1'},
      {'player_id': 'p2', 'name': 'Bilal Ahmed', 'position': 'DF', 'role': 'starter', 'squad_id': 'sq-1'},
      {'player_id': 'p3', 'name': 'Usman Tariq', 'position': 'MF', 'role': 'vice_captain', 'squad_id': 'sq-1'},
      {'player_id': 'p4', 'name': 'Hamza Raza', 'position': 'FW', 'role': 'substitute', 'squad_id': 'sq-1'},
    ],
    'club-2': [
      {'player_id': 'p5', 'name': 'Sana Iqbal', 'position': 'GK', 'role': 'captain', 'squad_id': 'sq-2'},
      {'player_id': 'p6', 'name': 'Zain Malik', 'position': 'FW', 'role': 'starter', 'squad_id': 'sq-2'},
    ],
    'club-3': [],
    'club-4': [],
  };

  Future<T> _wait<T>(T Function() fn) async {
    await Future.delayed(_delay);
    return fn();
  }

  @override
  Future<Session> login(String email, String password) => _wait(() {
        final u = _users[email.trim().toLowerCase().replaceFirst('@nascon.test', '@demo.com')];
        if (u == null || password.isEmpty) throw ApiException('INVALID_CREDENTIALS');
        return Session.fromJson({
          'token': 'mock-jwt',
          'role': u.$1,
          'user': {
            'id': 'user-${u.$1}',
            'email': email,
            'display_name': u.$2,
            'club_id': u.$3,
            'league_id': u.$4,
            'player_id': u.$1 == 'player' ? 'p4' : null,
          },
          'tenant': _tenant,
        });
      });

  @override
  Future<List<League>> leagues() => _wait(() => [
        League.fromJson({'league_id': 'lg-1', 'name': 'Premier Football League', 'sport_id': 'football', 'season': '2026'}),
        League.fromJson({'league_id': 'lg-2', 'name': 'Esports Cup', 'sport_id': 'esports', 'season': '2026'}),
      ]);

  @override
  Future<List<Fixture>> fixtures(String leagueId) =>
      _wait(() => leagueId == 'lg-1'
          ? [
              for (final f in _fixtures)
                Fixture.fromJson({
                  ...f,
                  'home_score': _matchJson(f['match_id'])['home']['score'],
                  'away_score': _matchJson(f['match_id'])['away']['score'],
                }),
            ]
          : <Fixture>[]);

  Map<String, dynamic> _matchJson(String matchId) {
    final fx = _fixtures.firstWhere((f) => f['match_id'] == matchId, orElse: () => throw ApiException('MATCH_NOT_FOUND'));
    final log = _events[matchId]!;
    final compensatedBy = <String, String>{};
    for (final e in log) {
      if (e['type'] == 'compensation') compensatedBy[e['payload']['compensates']] = e['event_id'];
    }
    var home = 0, away = 0;
    for (final e in log) {
      if (e['type'] == 'score' && !compensatedBy.containsKey(e['event_id'])) {
        e['payload']['team_id'] == fx['home'] ? home++ : away++;
      }
    }
    final status = fx['status'] as String;
    return {
      'match_id': matchId,
      'sport_id': 'football',
      'league_id': 'lg-1',
      'status': status,
      'outcome': status != 'completed' ? 'pending' : (home > away ? 'home_win' : (away > home ? 'away_win' : 'draw')),
      'winner_team_id': home == away ? null : (home > away ? fx['home'] : fx['away']),
      'home': {'team_id': fx['home'], 'name': fx['home_name'], 'score': home, 'fair_play': 0},
      'away': {'team_id': fx['away'], 'name': fx['away_name'], 'score': away, 'fair_play': 0},
      'version': log.length,
      'events': [
        for (var i = 0; i < log.length; i++)
          {
            ...log[i],
            'sequence': i + 1,
            'compensated': compensatedBy.containsKey(log[i]['event_id']),
            'compensated_by': compensatedBy[log[i]['event_id']],
          }
      ],
      'pinned_product': _pinned[matchId] == null
          ? null
          : _products.firstWhere((p) => p['product_id'] == _pinned[matchId]),
    };
  }

  @override
  Future<MatchDetail> match(String matchId) => _wait(() => MatchDetail.fromJson(_matchJson(matchId)));

  @override
  Future<Standings> standings(String leagueId) => _wait(() {
        if (leagueId != 'lg-1') return Standings(leagueId: leagueId, sportId: 'esports', qualificationSpots: 2, table: []);
        Map<String, dynamic> row(int rank, String id, int p, int w, int d, int l, int s, int c, String status) => {
              'rank': rank,
              'team_id': id,
              'team_name': _teamNames[id],
              'played': p,
              'won': w,
              'drawn': d,
              'lost': l,
              'scored': s,
              'conceded': c,
              'diff': s - c,
              'points': w * 3 + d,
              'fair_play': 0,
              'status': status,
              'resolved_by': null,
            };
        return Standings.fromJson({
          'league_id': 'lg-1',
          'sport_id': 'football',
          'qualification_spots': 2,
          'table': [
            row(1, 'club-3', 3, 3, 0, 0, 7, 1, 'clinched'),
            row(2, 'club-1', 3, 2, 0, 1, 5, 3, 'still_possible'),
            row(3, 'club-2', 3, 1, 0, 2, 3, 5, 'still_possible'),
            row(4, 'club-4', 3, 0, 0, 3, 1, 7, 'eliminated'),
          ],
        });
      });

  @override
  Future<Club> club(String clubId) => _wait(() {
        final name = _teamNames[clubId];
        if (name == null) throw ApiException('CLUB_NOT_FOUND');
        return Club.fromJson({
          'club_id': clubId,
          'name': name,
          'tenant_id': 'ten-1',
          'venue': {'name': 'Gaddafi Stadium', 'lat': 31.5136, 'lng': 74.3335},
          'socials': {'instagram': '@${clubId.replaceAll('-', '')}', 'x': '@${clubId.replaceAll('-', '')}_fc'},
          'staff': [
            {'name': 'Coach Imran', 'role': 'coach'},
            {'name': 'Sara Shah', 'role': 'manager'},
            {'name': 'Dr. Faisal', 'role': 'physio'},
          ],
          'roster': _rosters[clubId] ?? [],
          'stats': [
            {'season': '2025', 'played': 10, 'won': 6, 'drawn': 2, 'lost': 2},
            {'season': '2026', 'played': 3, 'won': 2, 'drawn': 0, 'lost': 1},
          ],
        });
      });

  @override
  Future<List<Product>> products({String? clubId}) => _wait(() => [for (final p in _products) Product.fromJson(p)]);

  @override
  Future<Order> checkout(Map<String, dynamic> body) => _wait(() {
        final token = body['payment']['token'];
        final items = <Map<String, dynamic>>[];
        var subtotal = 0;
        for (final item in (body['items'] as List)) {
          final v = _products
              .expand((p) => p['variants'] as List)
              .cast<Map<String, dynamic>>()
              .firstWhere((v) => v['variant_id'] == item['variant_id']);
          if (v['stock'] < item['quantity']) throw ApiException('OUT_OF_STOCK');
          items.add({'variant_id': v['variant_id'], 'quantity': item['quantity'], 'unit_price_minor': v['price_minor']});
          subtotal += (v['price_minor'] as int) * (item['quantity'] as int);
        }
        if (token == 'tok_declined') throw ApiException('PAYMENT_DECLINED');
        if (token == 'tok_capture_fail') throw ApiException('PAYMENT_CAPTURE_FAILED');
        final discount = body['discount_code'] == 'WELCOME10' ? subtotal * 10 ~/ 100 : 0;
        for (final item in items) {
          final v = _products
              .expand((p) => p['variants'] as List)
              .cast<Map<String, dynamic>>()
              .firstWhere((v) => v['variant_id'] == item['variant_id']);
          v['stock'] -= item['quantity'];
        }
        return Order.fromJson({
          'order_id': body['order_id'],
          'status': 'paid',
          'currency': 'PKR',
          'items': items,
          'subtotal_minor': subtotal,
          'discount_minor': discount,
          'total_minor': subtotal - discount,
          'receipt': {'pdf_base64': _mockPdf},
        });
      });

  @override
  Future<Map<String, dynamic>> postEvent(Map<String, dynamic> body) => _wait(() => _applyEvent(body));

  Map<String, dynamic> _applyEvent(Map<String, dynamic> body) {
    final matchId = body['match_id'] as String;
    final fx = _fixtures.firstWhere((f) => f['match_id'] == matchId, orElse: () => throw ApiException('MATCH_NOT_FOUND'));
    final log = _events[matchId]!;
    if (log.any((e) => e['event_id'] == body['event_id'])) throw ApiException('DUPLICATE_EVENT_ID');
    switch (body['type']) {
      case 'match_start':
        if (fx['status'] != 'upcoming') throw ApiException('ILLEGAL_TRANSITION');
        fx['status'] = 'in_progress';
      case 'match_end':
        if (fx['status'] != 'in_progress') throw ApiException('ILLEGAL_TRANSITION');
        fx['status'] = 'completed';
      case 'score':
        if (fx['status'] != 'in_progress') throw ApiException('MATCH_NOT_IN_PROGRESS');
      case 'compensation':
        final target = body['payload']['compensates'];
        if (log.any((e) => e['type'] == 'compensation' && e['payload']['compensates'] == target)) {
          throw ApiException('INVALID_COMPENSATION');
        }
    }
    log.add({'event_id': body['event_id'], 'type': body['type'], 'payload': body['payload']});
    _live.add({'type': 'match_update', 'match_id': matchId, 'data': {}});
    return {
      'event_id': body['event_id'],
      'match_id': matchId,
      'type': body['type'],
      'sequence': log.length,
      'match_version': log.length,
      'signature': 'mock-signature',
    };
  }

  @override
  Future<Map<String, dynamic>> rosterTransfer(Map<String, dynamic> body) => _wait(() => _applyTransfer(body));

  Map<String, dynamic> _applyTransfer(Map<String, dynamic> body) {
    final from = _rosters.values.firstWhere(
      (r) => r.any((p) => p['player_id'] == body['player_id'] && p['squad_id'] == body['from_squad_id']),
      orElse: () => throw ApiException('NOT_IN_SQUAD'),
    );
    final player = from.firstWhere((p) => p['player_id'] == body['player_id']);
    from.remove(player);
    if (body['type'] != 'release') {
      final toClub = 'club-${(body['to_squad_id'] as String).replaceFirst('sq-', '')}';
      _rosters[toClub]?.add({...player, 'squad_id': body['to_squad_id'], 'role': 'substitute'});
    }
    return {'request_id': body['request_id'], 'status': 'accepted', 'state': 'active', 'blocking_match_id': null};
  }

  @override
  Future<Map<String, dynamic>> sync(String deviceId, List<Map<String, dynamic>> actions) => _wait(() {
        final results = <Map<String, dynamic>>[];
        var order = 0;
        for (final a in actions) {
          order++;
          try {
            a['type'] == 'score_event' ? _applyEvent(a['payload']) : _applyTransfer(a['payload']);
            results.add({'action_id': a['action_id'], 'status': 'applied', 'resolution': 'appended', 'error_code': null, 'processed_order': order});
          } on ApiException catch (e) {
            results.add({'action_id': a['action_id'], 'status': 'rejected', 'resolution': 'server_wins', 'error_code': e.code, 'processed_order': order});
          }
        }
        return {
          'device_id': deviceId,
          'results': results,
          'summary': {
            'applied': results.where((r) => r['status'] == 'applied').length,
            'rejected': results.where((r) => r['status'] == 'rejected').length,
            'duplicate': 0,
          },
        };
      });

  @override
  Future<void> pinProduct(String matchId, String productId) => _wait(() {
        _pinned[matchId] = productId;
        _live.add({'type': 'product_pinned', 'match_id': matchId, 'data': {'product_id': productId}});
      });

  @override
  Future<List<String>> eventTypes(String sportId) => _wait(() => ['goal', 'penalty_goal', 'own_goal']);

  @override
  Future<List<Map<String, dynamic>>> squads(String leagueId) => _wait(() => [
        for (final e in _teamNames.entries) {'squad_id': 'sq-${e.key.replaceFirst('club-', '')}', 'name': e.value},
      ]);

  @override
  Stream<Map<String, dynamic>> liveUpdates() => _live.stream;

}

/// A tiny real PDF ("%PDF-1.4 ... MOCK RECEIPT ord-mock, Total PKR 4500.00").
const _mockPdf =
    'JVBERi0xLjQKMSAwIG9iago8PCAvVHlwZSAvQ2F0YWxvZyAvUGFnZXMgMiAwIFIgPj4KZW5kb2JqCjIgMCBvYmoKPDwgL1R5cGUgL1BhZ2VzIC9LaWRzIFszIDAgUl0gL0NvdW50IDEgPj4KZW5kb2JqCjMgMCBvYmoKPDwgL1R5cGUgL1BhZ2UgL1BhcmVudCAyIDAgUiAvTWVkaWFCb3ggWzAgMCAzMDAgMjAwXSAvQ29udGVudHMgNCAwIFIgL1Jlc291cmNlcyA8PCAvRm9udCA8PCAvRjEgNSAwIFIgPj4gPj4gPj4KZW5kb2JqCjQgMCBvYmoKPDwgL0xlbmd0aCA4NCA+PgpzdHJlYW0KQlQgL0YxIDE0IFRmIDIwIDE1MCBUZCAoTU9DSyBSRUNFSVBUIG9yZC1tb2NrKSBUaiAwIC0yNCBUZCAoVG90YWwgUEtSIDQ1MDAuMDApIFRqIEVUCmVuZHN0cmVhbQplbmRvYmoKNSAwIG9iago8PCAvVHlwZSAvRm9udCAvU3VidHlwZSAvVHlwZTEgL0Jhc2VGb250IC9IZWx2ZXRpY2EgPj4KZW5kb2JqCnhyZWYKMCA2CjAwMDAwMDAwMDAgNjU1MzUgZiAKMDAwMDAwMDAwOSAwMDAwMCBuIAowMDAwMDAwMDU4IDAwMDAwIG4gCjAwMDAwMDAxMTUgMDAwMDAgbiAKMDAwMDAwMDI0MSAwMDAwMCBuIAowMDAwMDAwMzc1IDAwMDAwIG4gCnRyYWlsZXIKPDwgL1NpemUgNiAvUm9vdCAxIDAgUiA+PgpzdGFydHhyZWYKNDQ1CiUlRU9GCg==';
