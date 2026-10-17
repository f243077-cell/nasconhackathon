import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/session.dart';
import '../../data/sync_queue.dart';
import '../../widgets/confirm_dialog.dart';
import '../../widgets/tenant_title.dart';

/// Role-filtered menu: Roster (manager), Scoring (organizer), Sync, Settings, Sign out.
class MoreScreen extends ConsumerWidget {
  const MoreScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(sessionProvider);
    final pending = ref.watch(syncProvider).pending.length;
    if (session == null) return const SizedBox.shrink();
    return Scaffold(
      appBar: AppBar(title: const TenantTitle('More')),
      body: ListView(children: [
        ListTile(
          leading: const CircleAvatar(child: Icon(Icons.person, semanticLabel: 'Profile')),
          title: Text(session.user.displayName),
          subtitle: Text('${session.roleLabel} · ${session.tenant.name}'),
        ),
        const Divider(),
        if (session.canManageRoster)
          ListTile(
            leading: const Icon(Icons.groups),
            title: const Text('Roster management'),
            subtitle: const Text('Transfer, loan or release players'),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => context.push('/roster'),
          ),
        if (session.canScore)
          ListTile(
            leading: const Icon(Icons.scoreboard),
            title: const Text('Scoring entry'),
            subtitle: const Text('Add score events and corrections'),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => context.push('/scoring'),
          ),
        ListTile(
          leading: const Icon(Icons.sync),
          title: const Text('Sync queue'),
          subtitle: Text(pending == 0 ? 'Nothing waiting to sync' : '$pending waiting to sync'),
          trailing: const Icon(Icons.chevron_right),
          onTap: () => context.push('/sync'),
        ),
        ListTile(
          leading: const Icon(Icons.settings),
          title: const Text('Settings'),
          subtitle: const Text('Server address'),
          trailing: const Icon(Icons.chevron_right),
          onTap: () => context.push('/settings'),
        ),
        const Divider(),
        ListTile(
          leading: const Icon(Icons.logout),
          title: const Text('Sign out'),
          onTap: () async {
            final ok = await confirmAction(context, title: 'Sign out?', message: 'You will need to sign in again.', confirmLabel: 'Sign out');
            if (ok) ref.read(sessionProvider.notifier).logout();
          },
        ),
      ]),
    );
  }
}
