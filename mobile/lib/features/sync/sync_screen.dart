import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/errors.dart';
import '../../core/format.dart';
import '../../data/models.dart';
import '../../data/sync_queue.dart';
import '../../widgets/async_view.dart';
import '../../widgets/status_chip.dart';

/// Pending-action queue, Sync now button and per-action results.
class SyncScreen extends ConsumerWidget {
  const SyncScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final sync = ref.watch(syncProvider);
    final controller = ref.read(syncProvider.notifier);
    final statusText = switch (sync.status) {
      NetStatus.online => 'Online',
      NetStatus.offline => "Offline. Actions are saved and will sync when you're back online.",
      NetStatus.syncing => 'Syncing…',
    };

    return Scaffold(
      appBar: AppBar(title: const Text('Sync queue')),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        Card(
          child: ListTile(
            leading: Icon(sync.isOffline ? Icons.cloud_off : Icons.cloud_done, semanticLabel: 'Connection'),
            title: Text(statusText),
            subtitle: Text('${sync.pending.length} pending'),
          ),
        ),
        // TODO(data layer): remove once connectivity_plus drives the status.
        SwitchListTile(
          title: const Text('Simulate offline (testing)'),
          value: sync.isOffline,
          onChanged: controller.setOffline,
        ),
        const SizedBox(height: 8),
        FilledButton.icon(
          onPressed: sync.status != NetStatus.online || sync.pending.isEmpty
              ? null
              : () async {
                  try {
                    await controller.syncNow();
                    if (context.mounted) showSuccess(context, 'Sync finished.');
                  } catch (e) {
                    if (context.mounted) showError(context, e);
                  }
                },
          icon: const Icon(Icons.sync),
          label: const Text('Sync now'),
        ),
        const SectionHeader('Pending'),
        if (sync.pending.isEmpty) const EmptyState(message: 'Nothing waiting to sync', icon: Icons.done_all),
        for (final a in sync.pending) _ActionTile(action: a),
        if (sync.results.isNotEmpty) ...[
          const SectionHeader('Last sync results'),
          for (final a in sync.results)
            _ActionTile(
              action: a,
              trailing: IconButton(
                tooltip: 'Dismiss',
                icon: const Icon(Icons.close),
                onPressed: () => controller.dismiss(a.actionId),
              ),
            ),
        ],
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
    final reason = action.status == 'rejected' ? 'Rejected: ${plainMessageForCode(action.errorCode)}' : null;
    return Card(
      child: ListTile(
        title: Text(humanize(action.summary)),
        subtitle: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('Queued ${formatDateTime(action.queuedAt)}'),
          if (reason != null) Text(reason),
          const SizedBox(height: 4),
          StatusChip.sync(action.status),
        ]),
        trailing: trailing,
        isThreeLine: true,
      ),
    );
  }
}
