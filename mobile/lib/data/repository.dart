import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/session.dart';
import 'api_repository.dart';
import 'models.dart';

/// The ONE contract the UI talks to. Screens never call dio/sqflite directly.
///
/// Backed by [ApiRepository]: the real /api/v1 backend with an sqflite cache (AGREED_RULES §4/§5).
abstract class AppRepository {
  Future<Session> login(String email, String password);
  Future<List<League>> leagues();
  Future<List<Fixture>> fixtures(String leagueId);
  Future<MatchDetail> match(String matchId);
  Future<Standings> standings(String leagueId);
  Future<Club> club(String clubId);
  Future<List<Product>> products({String? clubId});

  /// Body = CLAUDE.md §7.9 checkout request.
  Future<Order> checkout(Map<String, dynamic> body);

  /// Body = §7.6 event request. Returns the event response.
  Future<Map<String, dynamic>> postEvent(Map<String, dynamic> body);

  /// Body = §7.8 transfer request. Returns the transfer response.
  Future<Map<String, dynamic>> rosterTransfer(Map<String, dynamic> body);

  /// Body = §7.11 offline-sync request. Returns the full response ({device_id, results, summary}).
  Future<Map<String, dynamic>> sync(String deviceId, List<Map<String, dynamic>> actions);

  Future<void> pinProduct(String matchId, String productId);

  /// FR-1.3: postpone / abandon / cancel / reschedule (to: upcoming). Organizer only.
  Future<void> setMatchStatus(String matchId, String to, {String? reason});

  /// Scoring buttons come from the sport config, never hard-coded.
  Future<List<EventType>> eventTypes(String sportId);

  /// Squads in a league with their current players, for the transfer destination picker.
  Future<List<Map<String, dynamic>>> squads(String leagueId);

  /// Player's audit trail; its length is the base_version of an offline roster action.
  Future<RosterHistory> rosterHistory(String playerId);

  /// Server-generated PDF receipt (used when the checkout response had no pdf_base64).
  Future<List<int>> receiptPdf(String orderId);

  /// WS /api/v1/ws messages: {type: match_update|match_status|product_pinned, match_id, data}.
  Stream<Map<String, dynamic>> liveUpdates();
}

final repositoryProvider = Provider<AppRepository>(ApiRepository.new);

// ---- Read providers used by the screens ----

final leaguesProvider = FutureProvider<List<League>>((ref) => ref.watch(repositoryProvider).leagues());

final fixturesProvider =
    FutureProvider.family<List<Fixture>, String>((ref, leagueId) => ref.watch(repositoryProvider).fixtures(leagueId));

final matchProvider =
    FutureProvider.family<MatchDetail, String>((ref, matchId) => ref.watch(repositoryProvider).match(matchId));

final standingsProvider =
    FutureProvider.family<Standings, String>((ref, leagueId) => ref.watch(repositoryProvider).standings(leagueId));

final clubProvider = FutureProvider.family<Club, String>((ref, clubId) => ref.watch(repositoryProvider).club(clubId));

final productsProvider = FutureProvider<List<Product>>((ref) => ref.watch(repositoryProvider).products());

final productProvider = FutureProvider.family<Product, String>((ref, productId) async {
  final all = await ref.watch(productsProvider.future);
  return all.firstWhere((p) => p.productId == productId);
});

final eventTypesProvider =
    FutureProvider.family<List<EventType>, String>((ref, sportId) => ref.watch(repositoryProvider).eventTypes(sportId));

final squadsProvider = FutureProvider.family<List<Map<String, dynamic>>, String>(
    (ref, leagueId) => ref.watch(repositoryProvider).squads(leagueId));

final rosterHistoryProvider = FutureProvider.family<RosterHistory, String>(
    (ref, playerId) => ref.watch(repositoryProvider).rosterHistory(playerId));

final liveUpdatesProvider =
    StreamProvider<Map<String, dynamic>>((ref) => ref.watch(repositoryProvider).liveUpdates());

/// League chosen in the LeaguePicker (shared by Fixtures, Standings, Scoring).
/// null means "use the user's league, else the first league".
class SelectedLeague extends Notifier<String?> {
  @override
  String? build() => ref.watch(sessionProvider)?.user.leagueId;

  void select(String leagueId) => state = leagueId;
}

final selectedLeagueProvider = NotifierProvider<SelectedLeague, String?>(SelectedLeague.new);
