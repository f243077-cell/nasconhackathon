import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/session.dart';
import '../../core/theme.dart';
import '../../data/models.dart';
import '../../data/repository.dart';
import '../../data/sync_queue.dart';
import '../../widgets/async_view.dart';
import '../../widgets/club_cards.dart';
import '../../widgets/league_picker.dart';
import '../../widgets/player_card.dart';
import '../../widgets/sync_status_bar.dart';
import '../../widgets/team_crest.dart';
import '../../widgets/tenant_title.dart';
import '../../widgets/ui.dart';
import '../roster/roster_screen.dart';

/// Clubs tab: your own club's profile, or the league's clubs if you don't belong to one.
class ClubTab extends ConsumerWidget {
  const ClubTab({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final clubId = ref.watch(sessionProvider)?.user.clubId;
    if (clubId != null) return ClubProfile(clubId: clubId, asTab: true);
    final league = watchCurrentLeague(ref);
    return TabPage(
      title: 'Clubs',
      kicker: leagueKicker(league),
      onKickerTap: leagueSwitcher(context, ref),
      headerTrailing: const TenantMark(size: 34),
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
            emptyIcon: Icons.shield_outlined,
            builder: (s) => SliverList.list(children: [
              for (final r in [...s.table]..sort((a, b) => a.teamName.compareTo(b.teamName))) ...[
                Panel(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                  onTap: () => context.push('/club/${r.teamId}'),
                  child: Semantics(
                    button: true,
                    label: '${r.teamName}, ${ordinal(r.rank)} in the league',
                    excludeSemantics: true,
                    child: Row(children: [
                      TeamCrest(teamId: r.teamId, name: r.teamName, size: 34),
                      const SizedBox(width: 14),
                      Expanded(
                        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Text(r.teamName.toUpperCase(), style: condensed(20, weight: FontWeight.w700, color: context.palette.label)),
                          Text('${ordinal(r.rank)} in league · ${r.points} pts', style: TextStyle(fontSize: 13, color: context.palette.label3)),
                        ]),
                      ),
                      Icon(Icons.chevron_right_rounded, color: context.palette.muted),
                    ]),
                  ),
                ),
                const SizedBox(height: 10),
              ],
            ]),
          );
        }),
      ],
    );
  }
}

/// Pushed club profile (from Table, Fixtures or the club list).
class ClubScreen extends StatelessWidget {
  final String clubId;
  const ClubScreen({super.key, required this.clubId});

  @override
  Widget build(BuildContext context) => ClubProfile(clubId: clubId, asTab: false);
}

String ordinal(int n) {
  final suffix = (n % 100 >= 11 && n % 100 <= 13) ? 'th' : const {1: 'st', 2: 'nd', 3: 'rd'}[n % 10] ?? 'th';
  return '$n$suffix';
}

/// Club colour hero, then Squad / Staff / Venue / History. Managers of this club get
/// a floating "+ Roster action" button.
class ClubProfile extends ConsumerStatefulWidget {
  final String clubId;
  final bool asTab;
  const ClubProfile({super.key, required this.clubId, required this.asTab});

  @override
  ConsumerState<ClubProfile> createState() => _ClubProfileState();
}

class _ClubProfileState extends ConsumerState<ClubProfile> {
  int _tab = 0;

  @override
  Widget build(BuildContext context) {
    final session = ref.watch(sessionProvider);
    final club = ref.watch(clubProvider(widget.clubId));
    final canManage = (session?.canManageRoster ?? false) && session?.user.clubId == widget.clubId;
    final c = club.value;
    final p = context.palette;

    return Scaffold(
      floatingActionButton: canManage && c != null && c.roster.isNotEmpty
          ? FloatingActionButton.extended(
              backgroundColor: p.accent,
              foregroundColor: p.onAccent,
              elevation: 6,
              shape: const StadiumBorder(),
              onPressed: () => openRosterAction(context, ref, session!, c),
              label: Text('+ ROSTER ACTION', style: condensed(16, weight: FontWeight.w700, tracking: 1, color: p.onAccent)),
            )
          : null,
      body: AsyncView<Club>(
        value: club,
        onRetry: () => ref.invalidate(clubProvider(widget.clubId)),
        builder: (c) => RefreshIndicator(
          onRefresh: () => ref.refresh(clubProvider(widget.clubId).future),
          color: p.onAccent,
          backgroundColor: p.accent,
          child: ListView(
            padding: EdgeInsets.only(bottom: MediaQuery.paddingOf(context).bottom + 96),
            children: [
              _ClubHero(club: c, asTab: widget.asTab),
              UnderlineTabs(labels: const ['Squad', 'Staff', 'Venue', 'History'], index: _tab, onChanged: (i) => setState(() => _tab = i)),
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 4, 20, 0),
                child: switch (_tab) {
                  0 => _Squad(club: c, canManage: canManage),
                  1 => StaffList(club: c),
                  2 => VenueTab(club: c),
                  _ => HistoryTab(club: c),
                },
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ClubHero extends ConsumerWidget {
  final Club club;
  final bool asTab;
  const _ClubHero({required this.club, required this.asTab});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final p = context.palette;
    final color = TeamCrest.colorFor(club.clubId);
    final league = watchCurrentLeague(ref);
    final row = league == null
        ? null
        : ref.watch(standingsProvider(league.leagueId)).value?.table.where((r) => r.teamId == club.clubId).firstOrNull;
    final words = club.name.toUpperCase().split(' ');
    final title = words.length > 1 ? '${words.first}\n${words.skip(1).join(' ')}' : words.first;

    return Stack(children: [
      Positioned.fill(child: Opacity(opacity: 0.35, child: PitchBackdrop(glow: Colors.white))),
      Positioned.fill(
        child: DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [color.withValues(alpha: 0.55), color.withValues(alpha: 0.95)],
            ),
          ),
        ),
      ),
      SafeArea(
        bottom: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 4, 20, 20),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            asTab
                ? const ScreenHeader(leading: StatusPill(), trailing: TenantMark(size: 34))
                : const ScreenHeader(leading: BackChip(label: 'Clubs', filled: true, fallback: '/club'), trailing: StatusPill()),
            const SizedBox(height: 12),
            Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
              TeamCrest(teamId: club.clubId, name: club.name, size: 62),
              const SizedBox(width: 14),
              Expanded(
                child: Semantics(
                  header: true,
                  label: club.name,
                  child: ExcludeSemantics(
                    child: Text(title, style: condensed(42, weight: FontWeight.w800, color: Colors.white, height: 0.92)),
                  ),
                ),
              ),
            ]),
            const SizedBox(height: 14),
            Wrap(spacing: 16, runSpacing: 4, children: [
              Row(mainAxisSize: MainAxisSize.min, children: [
                const Icon(Icons.location_on_outlined, size: 16, color: Colors.white),
                const SizedBox(width: 4),
                Text(club.venueName, style: const TextStyle(fontSize: 14, color: Colors.white)),
              ]),
              if (row != null)
                Text('${ordinal(row.rank)} in league', style: TextStyle(fontSize: 14, color: p.label.withValues(alpha: 0.85))),
            ]),
          ]),
        ),
      ),
    ]);
  }
}

class _Squad extends ConsumerWidget {
  final Club club;
  final bool canManage;
  const _Squad({required this.club, required this.canManage});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (club.roster.isEmpty) return const EmptyState(message: 'No players yet', icon: Icons.groups_outlined);
    // Players with a roster move still in the offline queue.
    final waiting = {
      for (final a in ref.watch(syncProvider).pending)
        if (a.type == 'roster_transfer') '${a.payload['player_id']}',
    };
    final session = ref.watch(sessionProvider);
    final sorted = [...club.roster]..sort((a, b) {
        int rank(RosterPlayer p) => switch (p.role) { 'captain' => 0, 'vice_captain' => 1, _ => 2 };
        final r = rank(a).compareTo(rank(b));
        return r != 0 ? r : a.name.compareTo(b.name);
      });
    return Column(children: [
      for (var i = 0; i < sorted.length; i++)
        SquadRow(
          player: sorted[i],
          clubId: club.clubId,
          divider: i < sorted.length - 1,
          waitingToSync: waiting.contains(sorted[i].playerId),
          onTap: canManage ? () => openRosterAction(context, ref, session!, club, player: sorted[i]) : null,
        ),
      if (canManage)
        Padding(
          padding: const EdgeInsets.only(top: 12),
          child: Text(
            'Tap a player to transfer, loan or release them. Offline changes are saved and sync later.',
            style: TextStyle(fontSize: 13, color: context.palette.label3, height: 1.4),
          ),
        ),
    ]);
  }
}
