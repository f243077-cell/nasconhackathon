import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/sync_queue.dart';

/// Always-visible Online / Offline / Syncing indicator with the pending count.
/// Placed once in MaterialApp.builder (app.dart) so it is on EVERY screen.
class SyncStatusBar extends ConsumerWidget {
  final VoidCallback? onTap;
  const SyncStatusBar({super.key, this.onTap});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final sync = ref.watch(syncProvider);
    final (icon, text, color) = switch (sync.status) {
      NetStatus.online => (Icons.cloud_done, 'Online', Colors.green.shade800),
      NetStatus.offline => (Icons.cloud_off, 'Offline', Colors.grey.shade800),
      NetStatus.syncing => (Icons.sync, 'Syncing…', Colors.blue.shade800),
    };
    final pending = sync.pending.length;
    final label = pending == 0 ? text : '$text · $pending pending';
    return Material(
      color: color,
      child: InkWell(
        onTap: onTap,
        child: Semantics(
          label: 'Connection status: $label. Tap to open sync queue.',
          button: true,
          excludeSemantics: true,
          child: SizedBox(
            height: 32,
            width: double.infinity,
            child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
              Icon(icon, size: 16, color: Colors.white),
              const SizedBox(width: 8),
              Flexible(child: Text(label, style: const TextStyle(color: Colors.white, fontSize: 14), overflow: TextOverflow.ellipsis)),
            ]),
          ),
        ),
      ),
    );
  }
}
