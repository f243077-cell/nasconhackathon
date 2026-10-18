import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/config.dart';
import '../../core/session.dart';
import '../../core/theme.dart';
import '../../data/repository.dart';
import '../../data/sync_queue.dart';
import '../../widgets/confirm_dialog.dart';
import '../../widgets/player_card.dart';
import '../../widgets/team_crest.dart';
import '../../widgets/tenant_title.dart';
import '../../widgets/ui.dart';

/// Me tab: who you are, then sync, server, the tools your role can use, sign out.
class MoreScreen extends ConsumerStatefulWidget {
  const MoreScreen({super.key});

  @override
  ConsumerState<MoreScreen> createState() => _MoreScreenState();
}

class _MoreScreenState extends ConsumerState<MoreScreen> {
  String _server = '';

  @override
  void initState() {
    super.initState();
    _loadServer();
  }

  Future<void> _loadServer() async {
    final url = await ServerConfig.load();
    if (mounted) setState(() => _server = url.replaceFirst(RegExp(r'^https?://'), ''));
  }

  @override
  Widget build(BuildContext context) {
    final session = ref.watch(sessionProvider);
    final sync = ref.watch(syncProvider);
    if (session == null) return const SizedBox.shrink();
    final p = context.palette;
    final pending = sync.pending.length;
    final clubId = session.user.clubId;
    final club = clubId == null ? null : ref.watch(clubProvider(clubId)).value;

    return TabPage(
      title: 'Me',
      headerTrailing: const TenantMark(size: 34),
      slivers: [
        SliverList.list(children: [
          Panel(
            child: Row(children: [
              PlayerAvatar(playerId: session.user.playerId, name: session.user.displayName, clubId: clubId, size: 60),
              const SizedBox(width: 14),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(
                    session.user.displayName.toUpperCase(),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: condensed(24, weight: FontWeight.w800, color: p.label),
                  ),
                  Text(session.user.email, maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 14, color: p.label2)),
                  const SizedBox(height: 6),
                  Row(children: [
                    if (clubId != null) ...[
                      TeamCrest(teamId: clubId, name: club?.name ?? clubId, size: 16),
                      const SizedBox(width: 6),
                    ],
                    Flexible(
                      child: Text(
                        [session.roleLabel, club?.name ?? session.tenant.name].join(' · ').toUpperCase(),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: condensed(12, weight: FontWeight.w700, tracking: 1, color: p.accent),
                      ),
                    ),
                  ]),
                ]),
              ),
            ]),
          ),
          const SizedBox(height: 16),
          _Menu(children: [
            _MenuRow(
              title: 'Sync queue',
              trailing: pending == 0 ? null : Tag('$pending pending', color: p.warning, fontSize: 12),
              onTap: () => context.push('/sync'),
            ),
            _MenuRow(
              title: 'Server address',
              value: _server,
              onTap: () async {
                await context.push('/settings');
                _loadServer();
              },
            ),
            if (session.canScore) _MenuRow(title: 'Score entry', onTap: () => context.push('/scoring')),
            if (session.canManageRoster && clubId != null) _MenuRow(title: 'Manage roster', onTap: () => context.go('/club')),
            _MenuRow(
              title: 'Work offline',
              subtitle: 'Queue changes on this phone to test syncing',
              trailing: Switch(
                value: sync.status == NetStatus.offline && _forced,
                onChanged: (v) => setState(() {
                  _forced = v;
                  ref.read(syncProvider.notifier).setOffline(v);
                }),
              ),
            ),
          ]),
          const SizedBox(height: 16),
          SecondaryButton(
            label: 'Sign out',
            destructive: true,
            onPressed: () async {
              final ok = await confirmAction(
                context,
                title: 'Sign out?',
                message: "You'll need to sign in again to see your club.",
                confirmLabel: 'Sign out',
                destructive: true,
              );
              if (ok) ref.read(sessionProvider.notifier).logout();
            },
          ),
        ]),
      ],
    );
  }

  bool _forced = false;
}

class _Menu extends StatelessWidget {
  final List<Widget> children;
  const _Menu({required this.children});

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    return Panel(
      padding: EdgeInsets.zero,
      child: Column(children: [
        for (var i = 0; i < children.length; i++) ...[
          if (i > 0) Divider(height: 1, thickness: 1, color: p.raised),
          children[i],
        ],
      ]),
    );
  }
}

class _MenuRow extends StatelessWidget {
  final String title;
  final String? subtitle;
  final String? value;
  final Widget? trailing;
  final VoidCallback? onTap;
  const _MenuRow({required this.title, this.subtitle, this.value, this.trailing, this.onTap});

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    return InkWell(
      onTap: onTap,
      child: ConstrainedBox(
        constraints: const BoxConstraints(minHeight: 58),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          child: Row(children: [
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
                Text(title, style: TextStyle(fontSize: 16, color: p.label)),
                if (subtitle != null) Text(subtitle!, style: TextStyle(fontSize: 13, color: p.label3)),
              ]),
            ),
            if (value != null)
              Flexible(child: Text(value!, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 14, color: p.label3))),
            if (trailing != null) ...[const SizedBox(width: 8), trailing!],
            if (onTap != null) ...[const SizedBox(width: 8), Icon(Icons.chevron_right_rounded, color: p.muted)],
          ]),
        ),
      ),
    );
  }
}
