import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/format.dart';
import '../../core/session.dart';
import '../../core/theme.dart';
import '../../data/models.dart';
import '../../data/repository.dart';
import '../../widgets/async_view.dart';
import '../../widgets/league_picker.dart';
import '../../widgets/ui.dart';

/// Club tab: your own club, or the league's clubs if you don't belong to one.
class ClubTab extends ConsumerWidget {
  const ClubTab({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final clubId = ref.watch(sessionProvider)?.user.clubId;
    if (clubId != null) {
      return LargeTitlePage(
        title: 'Club',
        onRefresh: () => ref.refresh(clubProvider(clubId).future),
        slivers: [ClubView(clubId: clubId)],
      );
    }
    return LargeTitlePage(
      title: 'Clubs',
      onRefresh: () async {
        final id = await currentLeagueId(ref);
        if (id == null) return;
        ref.invalidate(standingsProvider(id));
        await ref.read(standingsProvider(id).future);
      },
      slivers: [
        LeagueScoped(builder: (context, league) {
          final standings = ref.watch(standingsProvider(league.leagueId));
          return AsyncSliver<Standings>(
            value: standings,
            onRetry: () => ref.invalidate(standingsProvider(league.leagueId)),
            isEmpty: (s) => s.table.isEmpty,
            emptyMessage: 'No clubs in this league yet',
            emptyIcon: Icons.shield_rounded,
            builder: (s) => SliverList.list(children: [
              Section(children: [
                for (final r in s.table)
                  ListTile(
                    leading: const Icon(Icons.shield_rounded),
                    title: Text(r.teamName),
                    trailing: Icon(Icons.chevron_right_rounded, color: context.palette.secondaryLabel.withValues(alpha: 0.6)),
                    onTap: () => context.push('/club/${r.teamId}'),
                  ),
              ]),
            ]),
          );
        }),
      ],
    );
  }
}

/// Pushed club profile (from Standings or the club list).
class ClubScreen extends ConsumerWidget {
  final String clubId;
  const ClubScreen({super.key, required this.clubId});

  @override
  Widget build(BuildContext context, WidgetRef ref) => Scaffold(
        appBar: AppBar(title: const Text('Club')),
        body: RefreshIndicator.adaptive(
          onRefresh: () => ref.refresh(clubProvider(clubId).future),
          child: CustomScrollView(slivers: [
            ClubView(clubId: clubId),
            const SliverToBoxAdapter(child: SizedBox(height: 32)),
          ]),
        ),
      );
}

/// Sliver: club header, then grouped facts. Used by the Club tab and the pushed profile.
class ClubView extends ConsumerWidget {
  final String clubId;
  const ClubView({super.key, required this.clubId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(sessionProvider);
    final club = ref.watch(clubProvider(clubId));
    final t = Theme.of(context).textTheme;
    final p = context.palette;
    return AsyncSliver<Club>(
      value: club,
      onRetry: () => ref.invalidate(clubProvider(clubId)),
      builder: (c) => SliverList.list(children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(32, 12, 32, 24),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(c.name, style: t.headlineMedium),
            const SizedBox(height: 4),
            Row(children: [
              Icon(Icons.location_on_rounded, size: 16, color: p.secondaryLabel),
              const SizedBox(width: 4),
              Flexible(child: Text(c.venueName, style: t.bodyMedium, overflow: TextOverflow.ellipsis)),
            ]),
          ]),
        ),
        if ((session?.canManageRoster ?? false) && session?.user.clubId == c.clubId)
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 28),
            child: PrimaryButton(label: 'Manage Roster', icon: Icons.groups_rounded, onPressed: () => context.push('/roster')),
          ),
        Section(
          header: 'Squad',
          children: c.roster.isEmpty
              ? [const ListTile(title: Text('No players yet'))]
              : [for (final pl in c.roster) PlayerTile(player: pl)],
        ),
        if (c.staff.isNotEmpty)
          Section(header: 'Staff', children: [
            for (final s in c.staff)
              ListTile(title: Text('${s['name']}'), trailing: Text(humanize('${s['role']}'))),
          ]),
        Section(header: 'Home Venue', children: [
          ListTile(
            title: Text(c.venueName),
            subtitle: c.lat == null
                ? null
                : Text('${c.lat!.toStringAsFixed(4)}, ${c.lng!.toStringAsFixed(4)}',
                    style: t.bodyMedium!.copyWith(fontFeatures: tabular)),
          ),
        ]),
        if (c.socials.isNotEmpty)
          Section(header: 'Social', children: [
            for (final s in c.socials.entries) ListTile(title: Text(humanize(s.key)), trailing: Text('${s.value}')),
          ]),
        if (c.stats.isNotEmpty)
          Section(header: 'Seasons', children: [
            for (final s in c.stats)
              ListTile(
                title: Text('${s['season']}'),
                trailing: Text(
                  '${s['won']}W  ${s['drawn']}D  ${s['lost']}L',
                  style: t.bodyLarge!.copyWith(color: p.secondaryLabel, fontFeatures: tabular),
                ),
                subtitle: Text('${s['played']} played'),
              ),
          ]),
      ]),
    );
  }
}

class PlayerTile extends StatelessWidget {
  final RosterPlayer player;
  final Widget? trailing;
  const PlayerTile({super.key, required this.player, this.trailing});

  @override
  Widget build(BuildContext context) => ListTile(
        title: Text(player.name),
        subtitle: Text(humanize(player.role)),
        trailing: trailing ??
            Text(player.position, style: Theme.of(context).textTheme.bodyLarge!.copyWith(color: context.palette.secondaryLabel)),
      );
}
