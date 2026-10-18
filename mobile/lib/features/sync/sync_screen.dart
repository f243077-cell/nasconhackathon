import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/errors.dart';
import '../../core/format.dart';
import '../../core/session.dart';
import '../../core/theme.dart';
import '../../data/models.dart';
import '../../data/repository.dart';
import '../../data/sync_queue.dart';
import '../../widgets/async_view.dart';
import '../../widgets/ui.dart';

/// Pending-action queue: counts, each action with its state, Sync now.
class SyncScreen extends ConsumerWidget {
  const SyncScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final sync = ref.watch(syncProvider);
    final controller = ref.read(syncProvider.notifier);
    final p = context.palette;
    final canSync = sync.status == NetStatus.online && sync.pending.isNotEmpty;
    final applied = sync.results.where((a) => a.status != 'rejected').length;
    final rejected = sync.results.where((a) => a.status == 'rejected').length;
    final detail = switch (sync.status) {
      NetStatus.online => 'Online. Changes are sent right away.',
      NetStatus.offline => 'Offline. Changes are saved on this phone and sync when you’re back online.',
      NetStatus.syncing => 'Sending your saved changes…',
    };

    // Player names for roster actions (the queue only stores ids).
    final clubId = ref.watch(sessionProvider)?.user.clubId;
    final names = {
      for (final pl in (clubId == null ? null : ref.watch(clubProvider(clubId)).value)?.roster ?? const <RosterPlayer>[])
        pl.playerId: pl.name,
    };

    Widget tile(int n, String label, Color c) => Expanded(
          child: Semantics(
            label: '$n $label',
            excludeSemantics: true,
            child: Panel(
              padding: const EdgeInsets.symmetric(vertical: 12),
              child: Column(children: [
                Text('$n', style: condensed(32, weight: FontWeight.w800, color: c, height: 1)),
                Text(label.toUpperCase(), style: condensed(12, weight: FontWeight.w600, tracking: 1, color: p.label3)),
              ]),
            ),
          ),
        );

    final rows = [...sync.pending, ...sync.results];
    return FlatPage(
      title: 'Sync queue',
      backLabel: 'Back',
      backFallback: '/more',
      statusLinksToQueue: false,
      actions: [
        PrimaryButton(
          label: 'Sync now',
          loading: sync.status == NetStatus.syncing,
          onPressed: !canSync
              ? null
              : () async {
                  try {
                    await controller.syncNow();
                    if (context.mounted) showSuccess(context, 'Sync finished.');
                  } catch (e) {
                    if (context.mounted) showError(context, e);
                  }
                },
        ),
      ],
      children: [
        Row(children: [
          tile(sync.pending.length, 'Pending', p.warning),
          const SizedBox(width: 8),
          tile(applied, 'Applied', p.accent),
          const SizedBox(width: 8),
          tile(rejected, 'Rejected', p.danger),
        ]),
        const SizedBox(height: 12),
        Text(detail, style: TextStyle(fontSize: 14, color: p.label2, height: 1.4)),
        const SizedBox(height: 8),
        if (rows.isEmpty)
          const EmptyState(message: 'Nothing waiting to sync', icon: Icons.cloud_done_outlined)
        else
          for (var i = 0; i < rows.length; i++)
            _ActionRow(
              action: rows[i],
              names: names,
              last: i == rows.length - 1,
              onDismiss: rows[i].status == 'pending' ? null : () => controller.dismiss(rows[i].actionId),
            ),
      ],
    );
  }
}

class _ActionRow extends StatelessWidget {
  final PendingAction action;
  final Map<String, String> names;
  final bool last;
  final VoidCallback? onDismiss;
  const _ActionRow({required this.action, required this.names, required this.last, this.onDismiss});

  /// "Goal · 72′" or "Transfer · Omar Shah".
  String get _title {
    final a = action;
    if (a.type == 'score_event') {
      final inner = a.payload['payload'] as Map? ?? const {};
      final what = a.payload['type'] == 'score' ? humanize('${inner['event_type']}') : humanize('${a.payload['type']}');
      return [what, if (inner['minute'] is num) '${inner['minute']}′'].join(' · ');
    }
    final who = names[a.payload['player_id']] ?? '${a.payload['player_id']}';
    return '${humanize('${a.payload['type']}')} · $who';
  }

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    final a = action;
    final kind = a.type == 'score_event' ? 'Score event' : 'Roster';
    final queued = parseLocal(a.queuedAt);
    final (tag, color) = switch (a.status) {
      'applied' => ('✓ Applied', p.accent),
      'duplicate' => ('✓ Already synced', p.label3),
      'rejected' => ('✕ Rejected', p.danger),
      _ => ('⟳ Pending', p.warning),
    };
    final sub = a.status == 'pending'
        ? '$kind · queued ${queued == null ? '' : formatClock(a.queuedAt)}'
        : a.status == 'rejected'
            ? plainMessageForCode(a.errorCode)
            : '$kind · synced';

    return Semantics(
      label: '$_title. $tag. $sub',
      excludeSemantics: onDismiss == null,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 12),
        decoration: BoxDecoration(border: last ? null : Border(bottom: BorderSide(color: p.hairline))),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                Expanded(child: Text(_title, style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700, color: p.label))),
                Text(tag.toUpperCase(), style: condensed(12, weight: FontWeight.w700, tracking: 1, color: color)),
              ]),
              const SizedBox(height: 2),
              Text(sub, style: TextStyle(fontSize: 13, height: 1.4, color: a.status == 'rejected' ? p.dangerSoft : p.label3)),
            ]),
          ),
          if (onDismiss != null)
            IconButton(
              tooltip: 'Dismiss',
              onPressed: onDismiss,
              icon: Icon(Icons.close_rounded, size: 18, color: p.label3),
            ),
        ]),
      ),
    );
  }
}
