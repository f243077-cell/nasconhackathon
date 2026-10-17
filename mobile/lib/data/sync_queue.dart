import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:uuid/uuid.dart';

import '../core/api_client.dart';
import '../core/errors.dart';
import '../core/format.dart';
import '../core/secure_store.dart';
import 'local_db.dart';
import 'models.dart';
import 'repository.dart';

enum NetStatus { online, offline, syncing }

class SyncState {
  final NetStatus status;
  final List<PendingAction> pending; // waiting to be sent
  final List<PendingAction> results; // last sync results (applied / rejected / duplicate)

  const SyncState({this.status = NetStatus.online, this.pending = const [], this.results = const []});

  bool get isOffline => status == NetStatus.offline;

  SyncState copyWith({NetStatus? status, List<PendingAction>? pending, List<PendingAction>? results}) =>
      SyncState(status: status ?? this.status, pending: pending ?? this.pending, results: results ?? this.results);
}

/// Online/offline status + the persistent pending-action queue (AGREED_RULES §5 "Sync", NFR-4).
///
/// - Online = the device has a network AND GET /api/v1/ping answers. Checked on every
///   connectivity change and every 15 s (well under the 100 req / 10 s limit).
/// - Every enqueue is written to SQLite first, so the queue survives a force-close.
/// - Coming back online syncs automatically; the Sync screen can also call [syncNow].
/// - Applied and duplicate actions leave the queue; rejected ones stay (persisted) until dismissed.
class SyncController extends Notifier<SyncState> {
  static const _uuid = Uuid();
  static const _probeEvery = Duration(seconds: 15);

  bool _forcedOffline = false; // manual "simulate offline" switch on the Sync screen
  bool _reachable = true;
  bool _syncing = false;
  StreamSubscription<List<ConnectivityResult>>? _connSub;
  Timer? _timer;

  @override
  SyncState build() {
    ref.onDispose(() {
      _connSub?.cancel();
      _timer?.cancel();
    });
    Future.microtask(_init);
    return const SyncState();
  }

  Future<void> _init() async {
    final saved = await LocalDb.loadActions();
    if (!ref.mounted) return;
    state = state.copyWith(
      pending: saved.where((a) => a.status == 'pending').toList(),
      results: saved.where((a) => a.status == 'rejected').toList(),
    );
    _connSub = Connectivity().onConnectivityChanged.listen((_) => _probe());
    _timer = Timer.periodic(_probeEvery, (_) => _probe());
    await _probe();
  }

  NetStatus get _netStatus => (_forcedOffline || !_reachable) ? NetStatus.offline : NetStatus.online;

  void _publishStatus() {
    if (!ref.mounted || _syncing) return;
    state = state.copyWith(status: _netStatus);
  }

  /// Network present and the backend answers /ping.
  Future<void> _probe() async {
    final net = await Connectivity().checkConnectivity();
    var ok = net.any((r) => r != ConnectivityResult.none);
    if (ok) {
      try {
        await ApiClient.get('/api/v1/ping', timeout: const Duration(seconds: 3));
      } on ApiException catch (e) {
        ok = e.code != 'OFFLINE'; // 429 etc. still means the server is there
      }
    }
    final cameBack = ok && !_reachable;
    _reachable = ok;
    _publishStatus();
    if (cameBack || (ok && state.pending.isNotEmpty)) await syncNow();
  }

  /// Re-test reachability now (e.g. after the server address changed).
  Future<void> recheck() => _probe();

  /// Called by the repository when a request could not reach the server.
  void reportUnreachable() {
    _reachable = false;
    _publishStatus();
  }

  /// Manual switch for testing/demo. Going online triggers an automatic sync.
  void setOffline(bool offline) {
    _forcedOffline = offline;
    _publishStatus();
    if (!offline) _probe();
  }

  /// Queues one action in the exact §7.11 format. Persisted before the UI shows "pending".
  Future<void> enqueue({required String type, required int baseVersion, required Map<String, dynamic> payload}) async {
    final action = PendingAction(
      actionId: _uuid.v4(),
      type: type,
      queuedAt: nowUtcIso(),
      baseVersion: baseVersion,
      payload: payload,
    );
    await LocalDb.saveAction(action);
    state = state.copyWith(pending: [...state.pending, action]);
  }

  Future<void> syncNow() async {
    if (_syncing || state.pending.isEmpty || _netStatus != NetStatus.online) return;
    _syncing = true;
    final sent = state.pending;
    state = state.copyWith(status: NetStatus.syncing);
    try {
      final deviceId = await SecureStore.deviceId();
      final response = await ref.read(repositoryProvider).sync(deviceId, [for (final a in sent) a.toJson()]);
      final byId = {for (final r in (response['results'] as List)) r['action_id']: r};
      final done = <PendingAction>[];
      for (final a in sent) {
        final r = byId[a.actionId];
        final result = a.withResult(r?['status'] ?? 'rejected', r?['error_code']);
        if (result.status == 'rejected') {
          await LocalDb.updateStatus(a.actionId, 'rejected', result.errorCode);
        } else {
          await LocalDb.deleteAction(a.actionId);
        }
        done.add(result);
      }
      final sentIds = {for (final a in sent) a.actionId};
      _syncing = false;
      state = state.copyWith(
        status: _netStatus,
        pending: state.pending.where((a) => !sentIds.contains(a.actionId)).toList(),
        results: [...done, ...state.results],
      );
    } on ApiException catch (e) {
      // Nothing was applied by us: keep the queue intact and try again later.
      _syncing = false;
      if (e.code == 'OFFLINE') _reachable = false;
      state = state.copyWith(status: _netStatus);
    } catch (_) {
      _syncing = false;
      state = state.copyWith(status: _netStatus);
    }
  }

  Future<void> dismiss(String actionId) async {
    await LocalDb.deleteAction(actionId);
    state = state.copyWith(results: state.results.where((a) => a.actionId != actionId).toList());
  }
}

final syncProvider = NotifierProvider<SyncController, SyncState>(SyncController.new);
