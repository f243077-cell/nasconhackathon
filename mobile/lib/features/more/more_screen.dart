import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/session.dart';
import '../../core/theme.dart';
import '../../data/sync_queue.dart';
import '../../widgets/confirm_dialog.dart';
import '../../widgets/tenant_title.dart';
import '../../widgets/ui.dart';

/// Account tab: who you are, then the tools your role can use (Roster, Scoring), Sync, Server, Sign Out.
class MoreScreen extends ConsumerWidget {
  const MoreScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(sessionProvider);
    final pending = ref.watch(syncProvider).pending.length;
    if (session == null) return const SizedBox.shrink();
    final p = context.palette;
    final t = Theme.of(context).textTheme;

    Widget row(IconData icon, String title, String route, {String? value}) => ListTile(
          leading: Icon(icon),
          title: Text(title),
          trailing: Row(mainAxisSize: MainAxisSize.min, children: [
            if (value != null) Text(value),
            const SizedBox(width: 4),
            Icon(Icons.chevron_right_rounded, color: p.secondaryLabel.withValues(alpha: 0.6)),
          ]),
          onTap: () => context.push(route),
        );

    return LargeTitlePage(
      title: 'Account',
      slivers: [
        SliverList.list(children: [
          const SizedBox(height: 12),
          Section(children: [
            Padding(
              padding: const EdgeInsets.all(16),
              child: Row(children: [
                const TenantMark(size: 52),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(session.user.displayName, style: t.headlineSmall, overflow: TextOverflow.ellipsis),
                    const SizedBox(height: 2),
                    Text('${session.roleLabel}, ${session.tenant.name}', style: t.bodyMedium),
                  ]),
                ),
              ]),
            ),
          ]),
          if (session.canManageRoster || session.canScore)
            Section(header: 'Manage', children: [
              if (session.canManageRoster) row(Icons.groups_rounded, 'Roster', '/roster'),
              if (session.canScore) row(Icons.scoreboard_rounded, 'Scoring', '/scoring'),
            ]),
          Section(children: [
            row(Icons.sync_rounded, 'Sync Queue', '/sync', value: pending == 0 ? null : '$pending pending'),
            row(Icons.dns_rounded, 'Server', '/settings'),
          ]),
          Section(children: [
            ListTile(
              title: Center(child: Text('Sign Out', style: TextStyle(color: p.danger))),
              onTap: () async {
                final ok = await confirmAction(
                  context,
                  title: 'Sign Out?',
                  message: "You'll need to sign in again to see your club.",
                  confirmLabel: 'Sign Out',
                  destructive: true,
                );
                if (ok) ref.read(sessionProvider.notifier).logout();
              },
            ),
          ]),
        ]),
      ],
    );
  }
}
