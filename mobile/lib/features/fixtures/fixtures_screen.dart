import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/format.dart';
import '../../core/theme.dart';
import '../../data/models.dart';
import '../../data/repository.dart';
import '../../widgets/async_view.dart';
import '../../widgets/league_picker.dart';
import '../../widgets/team_crest.dart';
import '../../widgets/tenant_title.dart';
import '../../widgets/ui.dart';

/// Fixtures: a strip of match days, the live match as a scoreboard card, then every other match
/// as a compact two-line card. Tapping a card opens the match.
class FixturesScreen extends ConsumerStatefulWidget {
  const FixturesScreen({super.key});

  @override
  ConsumerState<FixturesScreen> createState() => _FixturesScreenState();
}

class _FixturesScreenState extends ConsumerState<FixturesScreen> {
  DateTime? _day; // null = all days
  bool _dayChosen = false;

  @override
  Widget build(BuildContext context) {
    // Live scores and status changes arrive over the WebSocket; no polling.
    ref.listen(liveUpdatesProvider, (_, next) {
      final type = next.value?['type'];
      if (type == 'match_update' || type == 'match_status') ref.invalidate(fixturesProvider);
    });
    final league = watchCurrentLeague(ref);
    return TabPage(
      title: 'Fixtures',
      kicker: leagueKicker(league),
      onKickerTap: leagueSwitcher(context, ref),
      headerTrailing: const TenantMark(size: 34),
      onRefresh: () async {
        final id = await currentLeagueId(ref);
        if (id == null) return;
        ref.invalidate(fixturesProvider(id));
        await ref.read(fixturesProvider(id).future);
      },
      slivers: [
        LeagueScoped(builder: (context, league) {
          final fixtures = ref.watch(fixturesProvider(league.leagueId));
          return AsyncSliver<List<Fixture>>(
            value: fixtures,
            onRetry: () => ref.invalidate(fixturesProvider(league.leagueId)),
            isEmpty: (l) => l.isEmpty,
            emptyMessage: 'No matches yet',
            emptyIcon: Icons.calendar_month_rounded,
            builder: _list,
          );
        }),
      ],
    );
  }

  static DateTime? _dateOf(Fixture f) {
    final d = parseLocal(f.scheduledAt);
    return d == null ? null : DateTime(d.year, d.month, d.day);
  }

  Widget _list(List<Fixture> all) {
    final days = {for (final f in all) ?_dateOf(f)}.toList()..sort();
    // Open on the live match's day the first time; after that, the user's choice sticks.
    if (!_dayChosen) {
      final live = all.where((f) => f.status == 'in_progress').firstOrNull;
      _day = live == null ? null : _dateOf(live);
    }
    final shown = _day == null ? all : all.where((f) => _dateOf(f) == _day).toList();
    int rank(Fixture f) => switch (f.status) { 'in_progress' => 0, 'upcoming' => 1, 'postponed' => 2, 'completed' => 4, _ => 3 };
    final ordered = [...shown]..sort((a, b) {
        final r = rank(a).compareTo(rank(b));
        if (r != 0) return r;
        final c = (a.scheduledAt ?? '').compareTo(b.scheduledAt ?? '');
        return a.status == 'completed' ? -c : c; // newest results first
      });
    final open = ordered.where((f) => f.status != 'completed').toList();
    final results = ordered.where((f) => f.status == 'completed').toList();

    return SliverList.list(children: [
      if (days.isNotEmpty) ...[
        _DayStrip(
          days: days,
          selected: _day,
          onChanged: (d) => setState(() {
            _dayChosen = true;
            _day = d;
          }),
        ),
        const SizedBox(height: 16),
      ],
      // The day's matches cross-fade in when the day changes.
      SmoothSwitch(
        switchKey: _day,
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          if (ordered.isEmpty) const EmptyState(message: 'No matches on this day', icon: Icons.event_busy_rounded),
          for (final f in open) ...[
            f.status == 'in_progress' ? LiveFixtureCard(fixture: f) : FixtureCard(fixture: f),
            const SizedBox(height: 12),
          ],
          if (results.isNotEmpty) ...[
            SectionLabel('Results', padding: EdgeInsets.only(top: open.isEmpty ? 0 : 8, bottom: 10)),
            for (final f in results) ...[FixtureCard(fixture: f), const SizedBox(height: 12)],
          ],
        ]),
      ),
    ]);
  }
}

/// "ALL · SAT 10 · SAT 17 · SUN 18" — the selected day is an accent tile.
class _DayStrip extends StatelessWidget {
  final List<DateTime> days;
  final DateTime? selected;
  final ValueChanged<DateTime?> onChanged;
  const _DayStrip({required this.days, required this.selected, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    Widget tile({required String top, required String big, required bool on, required String semantics, required VoidCallback onTap}) =>
        Semantics(
          button: true,
          selected: on,
          label: semantics,
          excludeSemantics: true,
          child: GestureDetector(
            onTap: onTap,
            child: AnimatedContainer(
              duration: motion(context),
              curve: Curves.easeOutCubic,
              width: 58,
              margin: const EdgeInsets.only(right: 6),
              padding: const EdgeInsets.symmetric(vertical: 8),
              decoration: BoxDecoration(color: on ? p.accent : p.surface, borderRadius: BorderRadius.circular(10)),
              child: Column(children: [
                AnimatedDefaultTextStyle(
                  duration: motion(context),
                  style: condensed(12, weight: FontWeight.w600, color: on ? p.onAccent : p.label3),
                  child: Text(top.toUpperCase()),
                ),
                AnimatedDefaultTextStyle(
                  duration: motion(context),
                  style: condensed(20, weight: FontWeight.w700, color: on ? p.onAccent : p.label),
                  child: Text(big),
                ),
              ]),
            ),
          ),
        );
    return SizedBox(
      height: 58,
      child: ListView(scrollDirection: Axis.horizontal, clipBehavior: Clip.none, children: [
        tile(top: 'All', big: '${days.length}', on: selected == null, semantics: 'All match days', onTap: () => onChanged(null)),
        for (final d in days)
          tile(
            top: weekdayShort(d),
            big: '${d.day}',
            on: d == selected,
            semantics: '${formatDay(d)} ${monthShort(d)}',
            onTap: () => onChanged(d),
          ),
      ]),
    );
  }
}

/// The live match: accent-bordered card, crests either side of a big score.
class LiveFixtureCard extends StatelessWidget {
  final Fixture fixture;
  const LiveFixtureCard({super.key, required this.fixture});

  @override
  Widget build(BuildContext context) {
    final f = fixture;
    final p = context.palette;
    Widget side(String id, String name, CrossAxisAlignment align) => Expanded(
          child: Column(crossAxisAlignment: align, children: [
            TeamCrest(teamId: id, name: name, size: 38),
            const SizedBox(height: 8),
            Text(
              name.toUpperCase(),
              maxLines: 2,
              textAlign: align == CrossAxisAlignment.end ? TextAlign.end : TextAlign.start,
              style: condensed(18, weight: FontWeight.w700, color: p.label, height: 1),
            ),
          ]),
        );
    return Semantics(
      button: true,
      label: 'Live: ${f.homeName} ${f.homeScore ?? 0}, ${f.awayName} ${f.awayScore ?? 0}. Opens the match.',
      excludeSemantics: true,
      child: Panel(
        borderColor: p.accent,
        onTap: () => context.push('/match/${f.matchId}'),
        child: Column(children: [
          Row(children: [
            const MatchStatusLabel(status: 'in_progress'),
            const Spacer(),
            if (f.venue != null)
              Flexible(
                child: Text(
                  f.venue!.toUpperCase(),
                  overflow: TextOverflow.ellipsis,
                  style: condensed(13, weight: FontWeight.w600, tracking: 1, color: p.label3),
                ),
              ),
          ]),
          const SizedBox(height: 12),
          Row(crossAxisAlignment: CrossAxisAlignment.center, children: [
            side(f.home, f.homeName, CrossAxisAlignment.start),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8),
              child: Text.rich(
                TextSpan(children: [
                  TextSpan(text: '${f.homeScore ?? 0}'),
                  TextSpan(text: ' : ', style: TextStyle(color: p.muted)),
                  TextSpan(text: '${f.awayScore ?? 0}'),
                ]),
                style: condensed(52, weight: FontWeight.w800, color: p.label, height: 1),
              ),
            ),
            side(f.away, f.awayName, CrossAxisAlignment.end),
          ]),
        ]),
      ),
    );
  }
}

/// Upcoming, postponed or finished match: a status line, then one row per team.
class FixtureCard extends StatelessWidget {
  final Fixture fixture;
  const FixtureCard({super.key, required this.fixture});

  @override
  Widget build(BuildContext context) {
    final f = fixture;
    final p = context.palette;
    final day = parseLocal(f.scheduledAt);
    final (status, statusColor) = switch (f.status) {
      'postponed' => ('⏸ Postponed · new date TBC', p.warning),
      'completed' => ('Full time${day == null ? '' : ' · ${formatDay(day)}'}', p.label3),
      'upcoming' => ('${day == null ? 'Date TBC' : formatDay(day)} · Kick-off ${formatClock(f.scheduledAt)}', p.label3),
      _ => (humanize(f.status), p.warning),
    };
    final scored = f.hasScore && f.homeScore != null && f.awayScore != null;
    final homeWon = scored && f.status == 'completed' && f.homeScore! > f.awayScore!;
    final awayWon = scored && f.status == 'completed' && f.awayScore! > f.homeScore!;

    Widget team(String id, String name, String? trailing, {bool dim = false}) => Row(children: [
          TeamCrest(teamId: id, name: name, size: 22),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              name.toUpperCase(),
              overflow: TextOverflow.ellipsis,
              style: condensed(18, weight: FontWeight.w700, color: dim ? p.label3 : p.label),
            ),
          ),
          if (trailing != null)
            Text(trailing, style: condensed(trailing == 'VS' ? 14 : 20, weight: FontWeight.w700, color: trailing == 'VS' ? p.label3 : (dim ? p.label3 : p.label))),
        ]);

    final homeTrail = scored ? '${f.homeScore}' : (f.status == 'upcoming' ? 'VS' : '–');
    final awayTrail = scored ? '${f.awayScore}' : (f.status == 'upcoming' ? null : '–');
    return Semantics(
      button: true,
      label: '${f.homeName} versus ${f.awayName}, ${scored ? '${f.homeScore} to ${f.awayScore}, ' : ''}$status. Opens the match.',
      excludeSemantics: true,
      child: Panel(
        padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
        onTap: () => context.push('/match/${f.matchId}'),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Text(status.toUpperCase(), style: condensed(12, weight: FontWeight.w600, tracking: 1, color: statusColor)),
          const SizedBox(height: 8),
          team(f.home, f.homeName, homeTrail, dim: awayWon),
          const SizedBox(height: 8),
          team(f.away, f.awayName, awayTrail, dim: homeWon),
        ]),
      ),
    );
  }
}
