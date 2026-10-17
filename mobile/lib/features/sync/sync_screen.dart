import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/errors.dart';
import '../../core/format.dart';
import '../../core/theme.dart';
import '../../data/models.dart';
import '../../data/sync_queue.dart';
import '../../widgets/async_view.dart';
import '../../widgets/status_chip.dart';
import '../../widgets/ui.dart';

/// Pending-action queue, Sync Now and per-action results.
class SyncScreen extends ConsumerWidget {
  const SyncScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final sync = ref.watch(syncProvider);
    final controller = ref.read(syncProvider.notifier);
    final p = context.palette;
    final t = Theme.of(context).textTheme;
    final (icon, title, detail, tone) = switch (sync.status) {
      NetStatus.online => (Icons.check_circle_rounded, 'Online', 'Changes are sent right away.', p.success),
      NetStatus.offline => (Icons.cloud_off_rounded, 'Offline', 'Changes are saved on this phone and sync when you’re back online.', p.warning),
      NetStatus.syncing => (Icons.sync_rounded, 'Syncing', 'Sending your saved changes.', p.accent),
    };
    final canSync = sync.status == NetStatus.online && sync.pending.isNotEmpty;

    return Scaffold(
      appBar: AppBar(title: const Text('Sync')),
      bottomNavigationBar: sync.pending.isEmpty
          ? null
          : BottomActionBar(children: [
              PrimaryButton(
                label: 'Sync Now',
                icon: Icons.sync_rounded,
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
            ]),
      body: ListView(padding: const EdgeInsets.only(top: 12, bottom: 24), children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(32, 8, 32, 28),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Icon(icon, color: tone, size: 28),
              const SizedBox(width: 10),
              Text(title, style: t.headlineMedium),
            ]),
            const SizedBox(height: 6),
            Text(detail, style: t.bodyMedium),
          ]),
        ),
        if (sync.pending.isEmpty)
          const Section(header: 'Waiting to Sync', children: [ListTile(title: Text('Nothing waiting'))])
        else
          Section(header: 'Waiting to Sync', children: [for (final a in sync.pending) _ActionTile(action: a)]),
        if (sync.results.isNotEmpty)
          Section(header: 'Last Sync', children: [
            for (final a in sync.results)
              _ActionTile(
                action: a,
                trailing: IconButton(
                  tooltip: 'Dismiss',
                  icon: Icon(Icons.close_rounded, color: p.secondaryLabel),
                  onPressed: () => controller.dismiss(a.actionId),
                ),
              ),
          ]),
      ]),
    );
  }
}

class _ActionTile extends StatelessWidget {
  final PendingAction action;
  final Widget? trailing;
  const _ActionTile({required this.action, this.trailing});

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final reason = action.status == 'rejected' ? plainMessageForCode(action.errorCode) : null;
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 4, 12),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(humanize(action.summary), style: t.bodyLarge),
            const SizedBox(height: 2),
            Text('Saved ${formatDateTime(action.queuedAt)}', style: t.bodySmall),
            if (reason != null) ...[
              const SizedBox(height: 4),
              Text(reason, style: t.bodyMedium!.copyWith(color: context.palette.danger)),
            ],
            const SizedBox(height: 8),
            StatusChip.sync(action.status),
          ]),
        ),
        ?trailing,
      ]),
    );
  }
}
