import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:uuid/uuid.dart';

import '../core/format.dart';
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

/// Online/offline status + the pending-action queue (AGREED_RULES §5 "Sync").
///
// TODO(data layer, Huzaifa + Gunee):
//  - status from connectivity_plus + GET /api/v1/ping instead of [setOffline]
//  - write every enqueue to the sqflite `pending_actions` table BEFORE updating state (survives force-close)
//  - load the table in build(); device_id from flutter_secure_storage
class SyncController extends Notifier<SyncState> {
  static const _uuid = Uuid();
  String deviceId = 'dev-mock-1';

  @override
  SyncState build() => const SyncState();

  /// Testing switch until connectivity_plus is wired. Going online triggers an automatic sync.
  void setOffline(bool offline) {
    state = state.copyWith(status: offline ? NetStatus.offline : NetStatus.online);
    if (!offline && state.pending.isNotEmpty) syncNow();
  }

  /// Queues one action in the exact §7.11 format.
  Future<void> enqueue({required String type, required int baseVersion, required Map<String, dynamic> payload}) async {
    final action = PendingAction(
      actionId: _uuid.v4(),
      type: type,
      queuedAt: nowUtcIso(),
      baseVersion: baseVersion,
      payload: payload,
    );
    state = state.copyWith(pending: [...state.pending, action]);
  }

  Future<void> syncNow() async {
    if (state.pending.isEmpty || state.status != NetStatus.online) return;
    final sent = state.pending;
    state = state.copyWith(status: NetStatus.syncing);
    try {
      final response = await ref.read(repositoryProvider).sync(deviceId, [for (final a in sent) a.toJson()]);
      final byId = {for (final r in (response['results'] as List)) r['action_id']: r};
      final done = [
        for (final a in sent)
          a.withResult(byId[a.actionId]?['status'] ?? 'rejected', byId[a.actionId]?['error_code']),
      ];
      // Applied and duplicate items leave the queue; rejected ones stay visible in results until dismissed.
      state = state.copyWith(
        status: NetStatus.online,
        pending: state.pending.where((a) => !sent.contains(a)).toList(),
        results: [...done, ...state.results],
      );
    } catch (_) {
      state = state.copyWith(status: NetStatus.online);
      rethrow;
    }
  }

  void dismiss(String actionId) =>
      state = state.copyWith(results: state.results.where((a) => a.actionId != actionId).toList());
}

final syncProvider = NotifierProvider<SyncController, SyncState>(SyncController.new);
