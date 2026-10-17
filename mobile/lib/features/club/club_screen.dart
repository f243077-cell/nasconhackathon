import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/format.dart';
import '../../core/session.dart';
import '../../data/models.dart';
import '../../data/repository.dart';
import '../../widgets/async_view.dart';
import '../../widgets/league_picker.dart';
import '../../widgets/tenant_title.dart';

/// Club tab: your own club, or a list of clubs (from standings) if you don't have one.
class ClubTab extends ConsumerWidget {
  const ClubTab({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final clubId = ref.watch(sessionProvider)?.user.clubId;
    return Scaffold(
      appBar: AppBar(title: const TenantTitle('Club')),
      body: clubId != null
          ? ClubView(clubId: clubId)
          : LeagueScoped(builder: (context, league) {
              final standings = ref.watch(standingsProvider(league.leagueId));
              return AsyncView<Standings>(
                value: standings,
                onRetry: () => ref.invalidate(standingsProvider(league.leagueId)),
                isEmpty: (s) => s.table.isEmpty,
                emptyMessage: 'No clubs in this league yet',
                builder: (s) => ListView(children: [
                  for (final r in s.table)
                    ListTile(
                      leading: const Icon(Icons.shield),
                      title: Text(r.teamName),
                      trailing: const Icon(Icons.chevron_right),
                      onTap: () => context.push('/club/${r.teamId}'),
                    ),
                ]),
              );
            }),
    );
  }
}

/// Pushed club profile (from Standings / club list).
class ClubScreen extends StatelessWidget {
  final String clubId;
  const ClubScreen({super.key, required this.clubId});

  @override
  Widget build(BuildContext context) =>
      Scaffold(appBar: AppBar(title: const Text('Club profile')), body: ClubView(clubId: clubId));
}

class ClubView extends ConsumerWidget {
  final String clubId;
  const ClubView({super.key, required this.clubId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(sessionProvider);
    final club = ref.watch(clubProvider(clubId));
    return AsyncView<Club>(
      value: club,
      onRetry: () => ref.invalidate(clubProvider(clubId)),
      builder: (c) => RefreshIndicator(
        onRefresh: () => ref.refresh(clubProvider(clubId).future),
        child: ListView(padding: const EdgeInsets.only(bottom: 24), children: [
          ListTile(
            leading: const CircleAvatar(child: Icon(Icons.shield, semanticLabel: 'Club crest')),
            title: Text(c.name, style: Theme.of(context).textTheme.headlineSmall),
          ),
          if ((session?.canManageRoster ?? false) && session?.user.clubId == c.clubId)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: FilledButton.icon(
                onPressed: () => context.push('/roster'),
                icon: const Icon(Icons.groups),
                label: const Text('Manage roster'),
              ),
            ),
          const SectionHeader('Home venue'),
          ListTile(
            leading: const Icon(Icons.stadium),
            title: Text(c.venueName),
            subtitle: c.lat == null ? null : Text('${c.lat}, ${c.lng}'),
          ),
          if (c.socials.isNotEmpty) ...[
            const SectionHeader('Social'),
            for (final s in c.socials.entries)
              ListTile(leading: const Icon(Icons.alternate_email), title: Text('${s.value}'), subtitle: Text(humanize(s.key))),
          ],
          const SectionHeader('Staff'),
          if (c.staff.isEmpty) const ListTile(title: Text('No staff listed.')),
          for (final s in c.staff)
            ListTile(leading: const Icon(Icons.badge), title: Text('${s['name']}'), subtitle: Text(humanize('${s['role']}'))),
          const SectionHeader('Roster'),
          if (c.roster.isEmpty) const ListTile(title: Text('No players yet.')),
          for (final p in c.roster) PlayerTile(player: p),
          const SectionHeader('Season stats'),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: DataTable(columns: const [
              DataColumn(label: Text('Season')),
              DataColumn(label: Text('P'), numeric: true),
              DataColumn(label: Text('W'), numeric: true),
              DataColumn(label: Text('D'), numeric: true),
              DataColumn(label: Text('L'), numeric: true),
            ], rows: [
              for (final s in c.stats)
                DataRow(cells: [
                  DataCell(Text('${s['season']}')),
                  DataCell(Text('${s['played']}')),
                  DataCell(Text('${s['won']}')),
                  DataCell(Text('${s['drawn']}')),
                  DataCell(Text('${s['lost']}')),
                ]),
            ]),
          ),
        ]),
      ),
    );
  }
}

class PlayerTile extends StatelessWidget {
  final RosterPlayer player;
  final Widget? trailing;
  const PlayerTile({super.key, required this.player, this.trailing});

  @override
  Widget build(BuildContext context) => ListTile(
        leading: CircleAvatar(child: Text(player.position, style: const TextStyle(fontSize: 12))),
        title: Text(player.name),
        subtitle: Text('${humanize(player.role)} · ${player.position}'),
        trailing: trailing,
      );
}
