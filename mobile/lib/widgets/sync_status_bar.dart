import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/theme.dart';
import '../data/sync_queue.dart';

/// Online / Syncing / Offline pill with the pending count. It sits in the header of EVERY
/// screen (the Floodlight design's rule); tapping it opens the sync queue.
class StatusPill extends ConsumerWidget {
  /// False on the sync screen itself.
  final bool linkToQueue;
  const StatusPill({super.key, this.linkToQueue = true});

  static const _online = (Color(0xFF1C2A0E), Color(0xFFD4F56A), Color(0xFF4CC764));
  static const _syncing = (Color(0xFF13203A), Color(0xFFA9C8FF), Color(0xFF5B9BFF));
  static const _offline = (Color(0xFF2A2410), Color(0xFFF5C451), Color(0xFFF5A524));

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final sync = ref.watch(syncProvider);
    final n = sync.pending.length;
    final changes = n == 1 ? '1 change' : '$n changes';
    final ((bg, fg, dot), label) = switch (sync.status) {
      NetStatus.online => (_online, n == 0 ? 'Online · up to date' : 'Online · $n pending'),
      NetStatus.syncing => (_syncing, n == 0 ? 'Syncing…' : 'Syncing $changes…'),
      NetStatus.offline => (_offline, n == 0 ? 'Offline' : 'Offline · $n pending'),
    };
    final reduce = MediaQuery.of(context).disableAnimations;

    return Semantics(
      label: 'Connection status: $label.${linkToQueue ? ' Opens the sync queue.' : ''}',
      button: linkToQueue,
      liveRegion: true,
      excludeSemantics: true,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: linkToQueue ? () => context.push('/sync') : null,
        // 32 dp pill inside a 48 dp tap target.
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 8),
          child: AnimatedContainer(
            duration: reduce ? Duration.zero : const Duration(milliseconds: 250),
            height: 32,
            padding: const EdgeInsets.symmetric(horizontal: 14),
            decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(16)),
            child: Row(mainAxisSize: MainAxisSize.min, children: [
              Container(width: 8, height: 8, decoration: BoxDecoration(color: dot, shape: BoxShape.circle)),
              const SizedBox(width: 8),
              Text(
                label,
                maxLines: 1,
                style: TextStyle(fontFamily: bodyFont, fontSize: 13, fontWeight: FontWeight.w600, color: fg),
              ),
            ]),
          ),
        ),
      ),
    );
  }
}
