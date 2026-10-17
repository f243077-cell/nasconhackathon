import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/theme.dart';
import '../data/sync_queue.dart';

/// Always-visible Online / Offline / Syncing indicator with the pending count.
/// Placed once in MaterialApp.builder (app.dart) so it is on EVERY screen.
/// Quiet when online; tinted only when the state needs attention (alerts.md: "an indicator", not an alert).
class SyncStatusBar extends ConsumerWidget {
  final VoidCallback? onTap;
  const SyncStatusBar({super.key, this.onTap});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final p = context.palette;
    final sync = ref.watch(syncProvider);
    final (icon, text, tone) = switch (sync.status) {
      NetStatus.online => (Icons.check_circle_rounded, 'Online', p.success),
      NetStatus.offline => (Icons.cloud_off_rounded, 'Offline', p.warning),
      NetStatus.syncing => (Icons.sync_rounded, 'Syncing', p.accent),
    };
    final pending = sync.pending.length;
    final label = pending == 0 ? text : '$text, $pending pending';
    final reduce = MediaQuery.of(context).disableAnimations;
    final background = sync.status == NetStatus.online ? p.canvas : Color.alphaBlend(tone.withValues(alpha: 0.14), p.canvas);

    return AnimatedContainer(
      duration: reduce ? Duration.zero : const Duration(milliseconds: 250),
      curve: Curves.easeOut,
      color: background,
      child: Material(
        type: MaterialType.transparency,
        child: InkWell(
          onTap: onTap,
          child: Semantics(
            label: 'Connection status: $label. Opens the sync queue.',
            button: true,
            liveRegion: true,
            excludeSemantics: true,
            child: SizedBox(
              height: 32,
              width: double.infinity,
              child: AnimatedSwitcher(
                duration: reduce ? Duration.zero : const Duration(milliseconds: 200),
                child: Row(
                  key: ValueKey(label),
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(icon, size: 14, color: tone),
                    const SizedBox(width: 6),
                    Flexible(
                      child: Text(
                        label,
                        overflow: TextOverflow.ellipsis,
                        style: Theme.of(context).textTheme.labelMedium!.copyWith(color: p.label),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
