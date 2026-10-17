import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme.dart';
import '../../data/models.dart';
import '../../data/repository.dart';
import '../../widgets/async_view.dart';
import '../../widgets/league_picker.dart';
import '../../widgets/ui.dart';

/// Points table that fits a 360 dp phone without sideways scrolling.
/// Qualification status sits under the team name as icon + text.
class StandingsScreen extends ConsumerWidget {
  const StandingsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return LargeTitlePage(
      title: 'Standings',
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
            emptyMessage: 'No results yet.\nThe table appears after the first match.',
            emptyIcon: Icons.format_list_numbered_rounded,
            builder: (s) => SliverList.list(children: [
              Section(
                footer: 'Top ${s.qualificationSpots} qualify. P played, W won, D drawn, L lost, '
                    '+/- difference, Pts points. Tap a team for its club.',
                dividerIndent: 44,
                children: [
                  const _Header(),
                  for (final r in s.table) _StandingRow(row: r, qualifies: r.rank <= s.qualificationSpots),
                ],
              ),
            ]),
          );
        }),
      ],
    );
  }
}

const _numWidth = 30.0;

/// W/D/L only when there's room; on a 360 dp phone the team name keeps ~170 dp.
bool _wide(BuildContext context) => MediaQuery.sizeOf(context).width >= 420;

class _Header extends StatelessWidget {
  const _Header();

  @override
  Widget build(BuildContext context) {
    final style = Theme.of(context).textTheme.bodySmall!.copyWith(fontWeight: FontWeight.w600);
    Widget n(String s, String tip) => Tooltip(
          message: tip,
          child: SizedBox(width: _numWidth, child: Text(s, textAlign: TextAlign.end, style: style)),
        );
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 10, 16, 8),
      child: Row(children: [
        SizedBox(width: 28, child: Text('#', style: style)),
        Expanded(child: Text('Team', style: style)),
        n('P', 'Played'),
        if (_wide(context)) ...[n('W', 'Won'), n('D', 'Drawn'), n('L', 'Lost')],
        n('+/-', 'Difference'),
        SizedBox(width: 38, child: Text('Pts', textAlign: TextAlign.end, style: style)),
      ]),
    );
  }
}

class _StandingRow extends StatelessWidget {
  final StandingRow row;
  final bool qualifies;
  const _StandingRow({required this.row, required this.qualifies});

  @override
  Widget build(BuildContext context) {
    final r = row;
    final p = context.palette;
    final t = Theme.of(context).textTheme;
    final num = t.bodyMedium!.copyWith(color: p.label, fontFeatures: tabular);
    final (icon, label, color) = switch (r.status) {
      'clinched' => (Icons.check_circle_rounded, 'Clinched', p.success),
      'eliminated' => (Icons.cancel_rounded, 'Eliminated', p.danger),
      _ => (Icons.remove_circle_outline_rounded, 'In contention', p.warning),
    };
    Widget n(Object v) => SizedBox(width: _numWidth, child: Text('$v', textAlign: TextAlign.end, style: num));
    final diff = r.diff is int && (r.diff as int) > 0 ? '+${r.diff}' : '${r.diff}';

    return Semantics(
      button: true,
      label: 'Rank ${r.rank}, ${r.teamName}, ${r.points} points, $label',
      excludeSemantics: true,
      child: InkWell(
        onTap: () => context.push('/club/${r.teamId}'),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 11, 16, 11),
          child: Row(children: [
            SizedBox(
              width: 28,
              child: Text(
                '${r.rank}',
                style: t.titleMedium!.copyWith(fontFeatures: tabular, color: qualifies ? p.accent : p.secondaryLabel),
              ),
            ),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(r.teamName, style: t.bodyLarge, overflow: TextOverflow.ellipsis),
                const SizedBox(height: 2),
                Row(children: [
                  Icon(icon, size: 13, color: color),
                  const SizedBox(width: 4),
                  Flexible(
                    child: Text(label, overflow: TextOverflow.ellipsis, style: t.labelMedium!.copyWith(color: color)),
                  ),
                ]),
              ]),
            ),
            n(r.played),
            if (_wide(context)) ...[n(r.won), n(r.drawn), n(r.lost)],
            n(diff),
            SizedBox(
              width: 38,
              child: Text('${r.points}', textAlign: TextAlign.end, style: t.titleMedium!.copyWith(fontFeatures: tabular)),
            ),
          ]),
        ),
      ),
    );
  }
}
