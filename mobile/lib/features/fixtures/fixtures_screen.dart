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

/// Fixtures grouped Live / Upcoming / Results. Every match is one line
/// "[crest] Home  vs  [crest] Away" that expands in place into a face-off view.
class FixturesScreen extends ConsumerWidget {
  const FixturesScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return LargeTitlePage(
      title: 'Fixtures',
      trailing: const TenantMark(size: 30),
      onRefresh: () async {
        final id = await currentLeagueId(ref);
        if (id == null) return;
        ref.invalidate(fixturesProvider(id));
        await ref.read(fixturesProvider(id).future);
      },
      slivers: [
        LeagueScoped(builder: (context, league) {
          // Live scores and status changes arrive over the WebSocket; no polling.
          ref.listen(liveUpdatesProvider, (_, next) {
            final type = next.value?['type'];
            if (type == 'match_update' || type == 'match_status') ref.invalidate(fixturesProvider(league.leagueId));
          });
          final fixtures = ref.watch(fixturesProvider(league.leagueId));
          return AsyncSliver<List<Fixture>>(
            value: fixtures,
            onRetry: () => ref.invalidate(fixturesProvider(league.leagueId)),
            isEmpty: (l) => l.isEmpty,
            emptyMessage: 'No matches yet',
            emptyIcon: Icons.calendar_month_rounded,
            builder: (list) {
              final groups = [
                ('Live', list.where((f) => f.status == 'in_progress').toList()),
                ('Upcoming', list.where((f) => f.status == 'upcoming' || f.status == 'postponed').toList()),
                ('Results', list.where((f) => f.status == 'completed').toList()),
                ('Other', list.where((f) => !const {'in_progress', 'upcoming', 'postponed', 'completed'}.contains(f.status)).toList()),
              ];
              return SliverList.list(children: [
                for (final (title, items) in groups)
                  if (items.isNotEmpty)
                    Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                      Padding(
                        padding: const EdgeInsets.fromLTRB(20, 4, 20, 10),
                        child: Semantics(header: true, child: Text(title, style: Theme.of(context).textTheme.titleLarge)),
                      ),
                      Section(dividerIndent: 0, children: [for (final f in items) MatchRow(fixture: f)]),
                    ]),
              ]);
            },
          );
        }),
      ],
    );
  }
}

/// Collapsed: one line, crest + name on each side, "vs" (or the score) in the middle.
/// Tapped: drops down into crests at full size, names below them, a big VS/score between,
/// with the kick-off details and a button into the match.
class MatchRow extends StatefulWidget {
  final Fixture fixture;
  const MatchRow({super.key, required this.fixture});

  @override
  State<MatchRow> createState() => _MatchRowState();
}

class _MatchRowState extends State<MatchRow> {
  bool _open = false;

  @override
  Widget build(BuildContext context) {
    final f = widget.fixture;
    final t = Theme.of(context).textTheme;
    final p = context.palette;
    final reduce = MediaQuery.of(context).disableAnimations;
    final duration = reduce ? Duration.zero : const Duration(milliseconds: 300);
    final started = f.status != 'upcoming' && f.homeScore != null && f.awayScore != null;
    final middle = started ? '${f.homeScore} – ${f.awayScore}' : 'vs';

    final collapsed = Padding(
      padding: const EdgeInsets.fromLTRB(14, 12, 10, 12),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Row(children: [
          MatchStatusLabel(status: f.status, scheduledAt: f.scheduledAt),
          const SizedBox(width: 8),
          Expanded(child: Text(_dateLine(f), style: t.bodySmall, overflow: TextOverflow.ellipsis)),
          AnimatedRotation(
            turns: _open ? 0.5 : 0,
            duration: duration,
            child: Icon(Icons.keyboard_arrow_down_rounded, color: p.secondaryLabel, size: 22),
          ),
        ]),
        const SizedBox(height: 10),
        Row(children: [
          TeamCrest(teamId: f.home, name: f.homeName, size: 26),
          const SizedBox(width: 8),
          Expanded(child: Text(f.homeName, style: t.titleSmall, overflow: TextOverflow.ellipsis)),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 10),
            child: Text(
              middle,
              style: started
                  ? t.titleMedium!.copyWith(fontWeight: FontWeight.w800, fontFeatures: tabular)
                  : t.bodyMedium!.copyWith(fontWeight: FontWeight.w600),
            ),
          ),
          TeamCrest(teamId: f.away, name: f.awayName, size: 26),
          const SizedBox(width: 8),
          Expanded(child: Text(f.awayName, style: t.titleSmall, overflow: TextOverflow.ellipsis)),
        ]),
      ]),
    );

    Widget side(String id, String name) => Expanded(
          child: Column(children: [
            TeamCrest(teamId: id, name: name, size: 72),
            const SizedBox(height: 12),
            Text(name, textAlign: TextAlign.center, maxLines: 2, overflow: TextOverflow.ellipsis, style: t.titleMedium),
          ]),
        );

    final expanded = Padding(
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 18),
      child: Column(children: [
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          side(f.home, f.homeName),
          SizedBox(
            width: 104,
            child: Padding(
              padding: const EdgeInsets.only(top: 18),
              child: Column(children: [
                FittedBox(
                  fit: BoxFit.scaleDown,
                  child: Text(
                    started ? '${f.homeScore} – ${f.awayScore}' : 'VS',
                    style: t.headlineLarge!.copyWith(
                      fontSize: started ? 40 : 44,
                      fontWeight: FontWeight.w900,
                      letterSpacing: started ? -1 : 1,
                      fontFeatures: tabular,
                      color: started ? p.label : p.accent,
                      height: 1,
                    ),
                  ),
                ),
                const SizedBox(height: 10),
                MatchStatusLabel(status: f.status, scheduledAt: f.scheduledAt, large: true),
              ]),
            ),
          ),
          side(f.away, f.awayName),
        ]),
        if (f.venue != null) ...[
          const SizedBox(height: 16),
          Row(mainAxisAlignment: MainAxisAlignment.center, children: [
            Icon(Icons.location_on_rounded, size: 15, color: p.secondaryLabel),
            const SizedBox(width: 4),
            Flexible(child: Text('${f.venue}, ${formatDateTime(f.scheduledAt)}', style: t.bodySmall, overflow: TextOverflow.ellipsis)),
          ]),
        ],
        const SizedBox(height: 16),
        SecondaryButton(label: 'Match Details', onPressed: () => context.push('/match/${f.matchId}')),
      ]),
    );

    return Semantics(
      button: true,
      expanded: _open,
      label: '${f.homeName} versus ${f.awayName}, ${started ? 'score $middle, ' : ''}${formatDateTime(f.scheduledAt)}',
      child: InkWell(
        onTap: () => setState(() => _open = !_open),
        child: AnimatedSize(
          duration: duration,
          curve: Curves.easeOutCubic,
          alignment: Alignment.topCenter,
          child: Column(children: [
            collapsed,
            if (_open) expanded,
          ]),
        ),
      ),
    );
  }

  static const _days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  static const _months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  static String _dateLine(Fixture f) {
    final d = f.scheduledAt == null ? null : DateTime.tryParse(f.scheduledAt!)?.toLocal();
    if (d == null) return f.venue ?? '';
    return '${_days[d.weekday - 1]} ${d.day} ${_months[d.month - 1]}';
  }
}
