// Models mirror the /api/v1 response shapes in AGREED_RULES §4 (which reuse the
// /audit shapes in CLAUDE.md §7). Optional display names (team_name, name) fall
// back to ids when the backend does not send them.

class Tenant {
  final String tenantId;
  final String name;
  final String? logoUrl;
  final String? primaryColor;
  final String? secondaryColor;

  Tenant({required this.tenantId, required this.name, this.logoUrl, this.primaryColor, this.secondaryColor});

  factory Tenant.fromJson(Map<String, dynamic> j) => Tenant(
        tenantId: j['tenant_id'],
        name: j['name'],
        logoUrl: j['logo_url'],
        primaryColor: j['primary_color'],
        secondaryColor: j['secondary_color'],
      );
}

class AppUser {
  final String id;
  final String email;
  final String displayName;
  final String? clubId;
  final String? leagueId;
  final String? playerId;

  AppUser({required this.id, required this.email, required this.displayName, this.clubId, this.leagueId, this.playerId});

  factory AppUser.fromJson(Map<String, dynamic> j) => AppUser(
        id: j['id'],
        email: j['email'],
        displayName: j['display_name'] ?? j['email'],
        clubId: j['club_id'],
        leagueId: j['league_id'],
        playerId: j['player_id'],
      );
}

class Session {
  final String token;
  final String role; // super_admin | league_organizer | club_manager | player | viewer
  final AppUser user;
  final Tenant tenant;

  Session({required this.token, required this.role, required this.user, required this.tenant});

  factory Session.fromJson(Map<String, dynamic> j) => Session(
        token: j['token'],
        role: j['role'],
        user: AppUser.fromJson(j['user']),
        tenant: Tenant.fromJson(j['tenant']),
      );

  bool get canScore => role == 'league_organizer' || role == 'super_admin';
  bool get canManageRoster => role == 'club_manager' || role == 'super_admin';
  bool get canPinProduct => canScore || role == 'club_manager';

  String get roleLabel => const {
        'super_admin': 'Platform Admin',
        'league_organizer': 'League Organizer',
        'club_manager': 'Club Manager',
        'player': 'Player',
        'viewer': 'Viewer',
      }[role] ??
      role;
}

class League {
  final String leagueId;
  final String name;
  final String sportId;
  final String season;

  League({required this.leagueId, required this.name, required this.sportId, required this.season});

  factory League.fromJson(Map<String, dynamic> j) =>
      League(leagueId: j['league_id'], name: j['name'], sportId: j['sport_id'], season: '${j['season']}');
}

class Fixture {
  final String matchId;
  final String home;
  final String away;
  final String homeName;
  final String awayName;
  final String status;
  final String? scheduledAt;
  final String? venue;
  final num? homeScore; // optional: /api/v1 fixtures send home_score / away_score
  final num? awayScore;

  Fixture({
    required this.matchId,
    required this.home,
    required this.away,
    required this.homeName,
    required this.awayName,
    required this.status,
    this.scheduledAt,
    this.venue,
    this.homeScore,
    this.awayScore,
  });

  factory Fixture.fromJson(Map<String, dynamic> j) => Fixture(
        matchId: j['match_id'],
        home: j['home'],
        away: j['away'],
        homeName: j['home_name'] ?? j['home'],
        awayName: j['away_name'] ?? j['away'],
        status: j['status'],
        scheduledAt: j['scheduled_at'],
        venue: j['venue'],
        homeScore: j['home_score'],
        awayScore: j['away_score'],
      );
}

class TeamScore {
  final String teamId;
  final String name;
  final num score;
  final int? wickets;
  final int? balls;
  final String? overs;
  final int fairPlay;

  TeamScore({required this.teamId, required this.name, required this.score, this.wickets, this.balls, this.overs, this.fairPlay = 0});

  factory TeamScore.fromJson(Map<String, dynamic> j) => TeamScore(
        teamId: j['team_id'],
        name: j['name'] ?? j['team_id'],
        score: j['score'] ?? 0,
        wickets: j['wickets'],
        balls: j['balls'],
        overs: j['overs'],
        fairPlay: j['fair_play'] ?? 0,
      );

  /// "120/3 (14.2)" for innings sports, plain score otherwise.
  String get display => wickets == null ? '$score' : '$score/$wickets${overs == null ? '' : ' ($overs)'}';
}

class MatchEvent {
  final int sequence;
  final String eventId;
  final String type;
  final Map<String, dynamic> payload;
  final bool compensated;
  final String? compensatedBy;

  MatchEvent({required this.sequence, required this.eventId, required this.type, required this.payload, required this.compensated, this.compensatedBy});

  factory MatchEvent.fromJson(Map<String, dynamic> j) => MatchEvent(
        sequence: j['sequence'],
        eventId: j['event_id'],
        type: j['type'],
        payload: Map<String, dynamic>.from(j['payload'] ?? {}),
        compensated: j['compensated'] ?? false,
        compensatedBy: j['compensated_by'],
      );

  bool get canBeCompensated =>
      !compensated && (type == 'score' || type == 'discipline' || type == 'tiebreak_winner');
}

class MatchDetail {
  final String matchId;
  final String sportId;
  final String? leagueId;
  final String status; // upcoming | in_progress | completed
  final String outcome;
  final String? winnerTeamId;
  final TeamScore home;
  final TeamScore away;
  final int version;
  final List<MatchEvent> events;
  final Product? pinnedProduct;

  MatchDetail({
    required this.matchId,
    required this.sportId,
    this.leagueId,
    required this.status,
    required this.outcome,
    this.winnerTeamId,
    required this.home,
    required this.away,
    required this.version,
    required this.events,
    this.pinnedProduct,
  });

  factory MatchDetail.fromJson(Map<String, dynamic> j) => MatchDetail(
        matchId: j['match_id'],
        sportId: j['sport_id'],
        leagueId: j['league_id'],
        status: j['status'],
        outcome: j['outcome'] ?? 'pending',
        winnerTeamId: j['winner_team_id'],
        home: TeamScore.fromJson(j['home']),
        away: TeamScore.fromJson(j['away']),
        version: j['version'] ?? 0,
        events: [for (final e in (j['events'] as List? ?? [])) MatchEvent.fromJson(e)],
        pinnedProduct: j['pinned_product'] == null ? null : Product.fromJson(j['pinned_product']),
      );

  String teamName(String? teamId) => teamId == home.teamId ? home.name : (teamId == away.teamId ? away.name : (teamId ?? ''));
}

class StandingRow {
  final int rank;
  final String teamId;
  final String teamName;
  final int played, won, drawn, lost, scored, conceded, points;
  final num diff;
  final String status; // clinched | eliminated | still_possible

  StandingRow({
    required this.rank,
    required this.teamId,
    required this.teamName,
    required this.played,
    required this.won,
    required this.drawn,
    required this.lost,
    required this.scored,
    required this.conceded,
    required this.points,
    required this.diff,
    required this.status,
  });

  factory StandingRow.fromJson(Map<String, dynamic> j) => StandingRow(
        rank: j['rank'],
        teamId: j['team_id'],
        teamName: j['team_name'] ?? j['team_id'],
        played: j['played'],
        won: j['won'],
        drawn: j['drawn'],
        lost: j['lost'],
        scored: j['scored'],
        conceded: j['conceded'],
        points: j['points'],
        diff: j['diff'],
        status: j['status'],
      );
}

class Standings {
  final String leagueId;
  final String sportId;
  final int qualificationSpots;
  final List<StandingRow> table;

  Standings({required this.leagueId, required this.sportId, required this.qualificationSpots, required this.table});

  factory Standings.fromJson(Map<String, dynamic> j) => Standings(
        leagueId: j['league_id'],
        sportId: j['sport_id'],
        qualificationSpots: j['qualification_spots'] ?? 0,
        table: [for (final r in (j['table'] as List)) StandingRow.fromJson(r)],
      );
}

class RosterPlayer {
  final String playerId;
  final String name;
  final String position;
  final String role;
  final String squadId;

  RosterPlayer({required this.playerId, required this.name, required this.position, required this.role, required this.squadId});

  factory RosterPlayer.fromJson(Map<String, dynamic> j) =>
      RosterPlayer(playerId: j['player_id'], name: j['name'], position: j['position'], role: j['role'], squadId: j['squad_id']);
}

class Club {
  final String clubId;
  final String name;
  final String tenantId;
  final String venueName;
  final double? lat;
  final double? lng;
  final Map<String, dynamic> socials;
  final List<Map<String, dynamic>> staff; // {name, role}
  final List<RosterPlayer> roster;
  final List<Map<String, dynamic>> stats; // {season, played, won, drawn, lost}

  Club({
    required this.clubId,
    required this.name,
    required this.tenantId,
    required this.venueName,
    this.lat,
    this.lng,
    required this.socials,
    required this.staff,
    required this.roster,
    required this.stats,
  });

  factory Club.fromJson(Map<String, dynamic> j) {
    final venue = Map<String, dynamic>.from(j['venue'] ?? {});
    return Club(
      clubId: j['club_id'],
      name: j['name'],
      tenantId: j['tenant_id'],
      venueName: venue['name'] ?? 'Unknown venue',
      lat: (venue['lat'] as num?)?.toDouble(),
      lng: (venue['lng'] as num?)?.toDouble(),
      socials: Map<String, dynamic>.from(j['socials'] ?? {}),
      staff: [for (final s in (j['staff'] as List? ?? [])) Map<String, dynamic>.from(s)],
      roster: [for (final p in (j['roster'] as List? ?? [])) RosterPlayer.fromJson(p)],
      stats: [for (final s in (j['stats'] as List? ?? [])) Map<String, dynamic>.from(s)],
    );
  }
}

class Variant {
  final String variantId;
  final String? size;
  final String? color;
  final int priceMinor;
  final int stock;

  Variant({required this.variantId, this.size, this.color, required this.priceMinor, required this.stock});

  factory Variant.fromJson(Map<String, dynamic> j) =>
      Variant(variantId: j['variant_id'], size: j['size'], color: j['color'], priceMinor: j['price_minor'], stock: j['stock'] ?? 0);

  String get label => [size, color].whereType<String>().join(' / ');
}

class Product {
  final String productId;
  final String name;
  final String type; // apparel | accessory | digital
  final String? imageUrl;
  final List<Variant> variants;

  Product({required this.productId, required this.name, required this.type, this.imageUrl, required this.variants});

  factory Product.fromJson(Map<String, dynamic> j) => Product(
        productId: j['product_id'],
        name: j['name'],
        type: j['type'] ?? 'apparel',
        imageUrl: j['image_url'],
        variants: [for (final v in (j['variants'] as List? ?? [])) Variant.fromJson(v)],
      );

  int get fromPriceMinor => variants.isEmpty ? 0 : variants.map((v) => v.priceMinor).reduce((a, b) => a < b ? a : b);
}

/// Successful checkout response (CLAUDE.md §7.9).
class Order {
  final String orderId;
  final String status;
  final String currency;
  final List<Map<String, dynamic>> items; // {variant_id, quantity, unit_price_minor}
  final int subtotalMinor, discountMinor, totalMinor;
  final String? pdfBase64;

  Order({
    required this.orderId,
    required this.status,
    required this.currency,
    required this.items,
    required this.subtotalMinor,
    required this.discountMinor,
    required this.totalMinor,
    this.pdfBase64,
  });

  factory Order.fromJson(Map<String, dynamic> j) => Order(
        orderId: j['order_id'],
        status: j['status'],
        currency: j['currency'] ?? 'PKR',
        items: [for (final i in (j['items'] as List? ?? [])) Map<String, dynamic>.from(i)],
        subtotalMinor: j['subtotal_minor'],
        discountMinor: j['discount_minor'],
        totalMinor: j['total_minor'],
        pdfBase64: j['receipt']?['pdf_base64'],
      );
}

/// One offline queue item. toJson() is EXACTLY the §7.11 action format.
class PendingAction {
  final String actionId;
  final String type; // score_event | roster_transfer
  final String queuedAt;
  final int baseVersion;
  final Map<String, dynamic> payload;
  final String status; // pending | applied | rejected | duplicate
  final String? errorCode;

  PendingAction({
    required this.actionId,
    required this.type,
    required this.queuedAt,
    required this.baseVersion,
    required this.payload,
    this.status = 'pending',
    this.errorCode,
  });

  Map<String, dynamic> toJson() =>
      {'action_id': actionId, 'type': type, 'queued_at': queuedAt, 'base_version': baseVersion, 'payload': payload};

  PendingAction withResult(String status, String? errorCode) => PendingAction(
        actionId: actionId,
        type: type,
        queuedAt: queuedAt,
        baseVersion: baseVersion,
        payload: payload,
        status: status,
        errorCode: errorCode,
      );

  /// Short human description, e.g. "Score: goal" or "Roster: release".
  String get summary {
    if (type != 'score_event') return 'Roster: ${payload['type']}';
    if (payload['type'] != 'score') return 'Score: ${payload['type']}';
    final inner = payload['payload'] as Map? ?? const {};
    return 'Score: ${inner['event_type']}';
  }
}
