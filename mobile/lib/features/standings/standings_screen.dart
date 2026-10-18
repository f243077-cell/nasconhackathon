import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme.dart';
import '../../data/models.dart';
import '../../data/repository.dart';
import '../../widgets/async_view.dart';
import '../../widgets/league_picker.dart';
import '../../widgets/team_crest.dart';
import '../../widgets/tenant_title.dart';
import '../../widgets/ui.dart';

/// Points table that fits a 360 dp phone: rank, crest, club (with its qualification state), P, GD, Pts.
/// A dashed line marks the qualification cut-off.
class StandingsScreen extends ConsumerWidget {
  const StandingsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final league = watchCurrentLeague(ref);
    return TabPage(
      title: 'Table',
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
            emptyMessage: 'No results yet.\nThe table appears after the first match.',
            emptyIcon: Icons.sort_rounded,
            builder: (s) => SliverList.list(children: [
              const _Header(),
              for (final r in s.table) ...[
                _StandingRow(row: r, qualifies: r.rank <= s.qualificationSpots, first: r.rank == 1 || r.rank == s.qualificationSpots + 1),
                if (r.rank == s.qualificationSpots && r.rank < s.table.length) const _QualificationLine(),
              ],
              const SizedBox(height: 16),
              Row(children: [
                Expanded(
                  child: SecondaryButton(
                    label: 'Head-to-head',
                    height: 48,
                    onPressed: () => showModalBottomSheet<void>(
                      context: context,
                      isScrollControlled: true,
                      useSafeArea: true,
                      builder: (_) => HeadToHeadSheet(leagueId: league.leagueId, table: s.table),
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: SecondaryButton(
                    label: 'Tie-break rules',
                    height: 48,
                    onPressed: () => showModalBottomSheet<void>(
                      context: context,
                      isScrollControlled: true,
                      useSafeArea: true,
                      builder: (_) => _RulesSheet(qualificationSpots: s.qualificationSpots),
                    ),
                  ),
                ),
              ]),
            ]),
          );
        }),
      ],
    );
  }
}

// Column widths: rank, crest, club (flex), P, GD, Pts.
const _rankW = 28.0, _crestW = 26.0, _pW = 24.0, _gdW = 34.0, _ptsW = 34.0, _gap = 8.0;

class _Header extends StatelessWidget {
  const _Header();

  @override
  Widget build(BuildContext context) {
    final style = condensed(12, weight: FontWeight.w600, tracking: 1, color: context.palette.label3);
    Widget n(String s, double w, String tip, {TextAlign align = TextAlign.center}) =>
        Tooltip(message: tip, child: SizedBox(width: w, child: Text(s, textAlign: align, style: style)));
    return ExcludeSemantics(
      child: Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: Row(children: [
          const SizedBox(width: _rankW + _gap + _crestW + _gap),
          Expanded(child: Text('CLUB', style: style)),
          n('P', _pW, 'Played'),
          const SizedBox(width: _gap),
          n('GD', _gdW, 'Goal difference'),
          const SizedBox(width: _gap),
          n('PTS', _ptsW, 'Points', align: TextAlign.end),
        ]),
      ),
    );
  }
}

class _StandingRow extends StatelessWidget {
  final StandingRow row;
  final bool qualifies;
  final bool first; // no top rule under the header or the qualification line
  const _StandingRow({required this.row, required this.qualifies, required this.first});

  @override
  Widget build(BuildContext context) {
    final r = row;
    final p = context.palette;
    final (label, color) = switch (r.status) {
      'clinched' => ('✓ Qualified', p.accent),
      'eliminated' => ('✕ Eliminated', p.danger),
      _ => qualifies ? ('✓ Qualifying', p.accent) : ('Still in contention', p.label3),
    };
    final diff = r.diff > 0 ? '+${r.diff}' : (r.diff < 0 ? '−${-r.diff}' : '0');
    final num = TextStyle(fontSize: 15, color: p.label, fontFeatures: tabular);

    return Semantics(
      button: true,
      label: 'Rank ${r.rank}, ${r.teamName}, ${r.played} played, goal difference $diff, ${r.points} points, $label',
      excludeSemantics: true,
      child: InkWell(
        onTap: () => context.push('/club/${r.teamId}'),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 12),
          decoration: BoxDecoration(border: first ? null : Border(top: BorderSide(color: p.raised))),
          child: Row(children: [
            SizedBox(
              width: _rankW,
              child: Text('${r.rank}', style: condensed(28, weight: FontWeight.w800, color: qualifies ? p.accent : p.muted, height: 1)),
            ),
            const SizedBox(width: _gap),
            TeamCrest(teamId: r.teamId, name: r.teamName, size: _crestW),
            const SizedBox(width: _gap),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(
                  r.teamName.toUpperCase(),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: condensed(18, weight: FontWeight.w700, color: p.label, height: 1.2),
                ),
                Text(label, style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: color)),
              ]),
            ),
            SizedBox(width: _pW, child: Text('${r.played}', textAlign: TextAlign.center, style: num)),
            const SizedBox(width: _gap),
            SizedBox(width: _gdW, child: Text(diff, textAlign: TextAlign.center, style: num)),
            const SizedBox(width: _gap),
            SizedBox(
              width: _ptsW,
              child: Text('${r.points}', textAlign: TextAlign.end, style: condensed(22, weight: FontWeight.w800, color: p.label)),
            ),
          ]),
        ),
      ),
    );
  }
}

/// "- - - QUALIFICATION LINE - - -"
class _QualificationLine extends StatelessWidget {
  const _QualificationLine();

  @override
  Widget build(BuildContext context) {
    final c = context.palette.accent;
    Widget dashes() => Expanded(child: CustomPaint(size: const Size(double.infinity, 2), painter: _Dashes(c)));
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(children: [
        dashes(),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 8),
          child: Text('QUALIFICATION LINE', style: condensed(11, weight: FontWeight.w600, tracking: 1.5, color: c)),
        ),
        dashes(),
      ]),
    );
  }
}

class _Dashes extends CustomPainter {
  final Color color;
  _Dashes(this.color);

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..strokeWidth = 2;
    for (var x = 0.0; x < size.width; x += 10) {
      canvas.drawLine(Offset(x, size.height / 2), Offset((x + 6).clamp(0, size.width), size.height / 2), paint);
    }
  }

  @override
  bool shouldRepaint(_Dashes old) => old.color != color;
}

/// Pick two clubs, see every finished meeting between them this season.
class HeadToHeadSheet extends ConsumerStatefulWidget {
  final String leagueId;
  final List<StandingRow> table;
  const HeadToHeadSheet({super.key, required this.leagueId, required this.table});

  @override
  ConsumerState<HeadToHeadSheet> createState() => _HeadToHeadSheetState();
}

class _HeadToHeadSheetState extends ConsumerState<HeadToHeadSheet> {
  late String _a = widget.table.first.teamId;
  late String _b = widget.table.length > 1 ? widget.table[1].teamId : widget.table.first.teamId;

  String _name(String id) => widget.table.firstWhere((r) => r.teamId == id, orElse: () => widget.table.first).teamName;

  Future<void> _pick(bool first) async {
    final id = await showChoiceSheet<String>(
      context,
      title: 'Choose a club',
      selected: first ? _a : _b,
      leading: (id) => TeamCrest(teamId: id, name: _name(id), size: 24),
      options: [for (final r in widget.table) (r.teamId, r.teamName)],
    );
    if (id != null) setState(() => first ? _a = id : _b = id);
  }

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    final fixtures = ref.watch(fixturesProvider(widget.leagueId));
    Widget picker(bool first) {
      final id = first ? _a : _b;
      return Expanded(
        child: PickerField(leading: TeamCrest(teamId: id, name: _name(id), size: 24), text: _name(id), onTap: () => _pick(first)),
      );
    }

    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
      child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Text('HEAD-TO-HEAD', style: condensed(30, weight: FontWeight.w800, color: p.label)),
        const SizedBox(height: 14),
        Row(children: [picker(true), const SizedBox(width: 8), picker(false)]),
        const SizedBox(height: 14),
        fixtures.when(
          loading: () => const Padding(padding: EdgeInsets.all(24), child: LoadingView()),
          error: (_, _) => Text('Results are not available right now.', style: TextStyle(color: p.label3)),
          data: (all) {
            final meetings = all
                .where((f) => f.status == 'completed' && {f.home, f.away}.containsAll({_a, _b}) && _a != _b)
                .toList();
            if (meetings.isEmpty) {
              return Padding(
                padding: const EdgeInsets.symmetric(vertical: 20),
                child: Text(_a == _b ? 'Choose two different clubs.' : 'These clubs haven’t met yet this season.',
                    textAlign: TextAlign.center, style: TextStyle(color: p.label3)),
              );
            }
            var aWins = 0, bWins = 0, draws = 0;
            for (final f in meetings) {
              final aScore = f.home == _a ? f.homeScore ?? 0 : f.awayScore ?? 0;
              final bScore = f.home == _b ? f.homeScore ?? 0 : f.awayScore ?? 0;
              if (aScore > bScore) {
                aWins++;
              } else if (bScore > aScore) {
                bWins++;
              } else {
                draws++;
              }
            }
            Widget tally(String n, String label) => Expanded(
                  child: Panel(
                    padding: const EdgeInsets.symmetric(vertical: 12),
                    child: Column(children: [
                      Text(n, style: condensed(30, weight: FontWeight.w800, color: p.label, height: 1)),
                      Text(label.toUpperCase(), style: condensed(12, weight: FontWeight.w600, tracking: 1, color: p.label3)),
                    ]),
                  ),
                );
            return Column(children: [
              Row(children: [
                tally('$aWins', '${_name(_a)} wins'),
                const SizedBox(width: 8),
                tally('$draws', 'Draws'),
                const SizedBox(width: 8),
                tally('$bWins', '${_name(_b)} wins'),
              ]),
              const SizedBox(height: 8),
              for (final f in meetings)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 8),
                  child: Row(children: [
                    Expanded(child: Text(f.homeName, textAlign: TextAlign.end, style: TextStyle(color: p.label))),
                    Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 12),
                      child: Text('${f.homeScore ?? 0}–${f.awayScore ?? 0}', style: condensed(20, weight: FontWeight.w800, color: p.label)),
                    ),
                    Expanded(child: Text(f.awayName, style: TextStyle(color: p.label))),
                  ]),
                ),
            ]);
          },
        ),
      ]),
    );
  }
}

class _RulesSheet extends StatelessWidget {
  final int qualificationSpots;
  const _RulesSheet({required this.qualificationSpots});

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    Widget rule(String n, String text) => Padding(
          padding: const EdgeInsets.symmetric(vertical: 6),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            SizedBox(width: 28, child: Text(n, style: condensed(18, weight: FontWeight.w800, color: p.accent))),
            Expanded(child: Text(text, style: TextStyle(fontSize: 15, color: p.label, height: 1.35))),
          ]),
        );
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('TIE-BREAK RULES', style: condensed(30, weight: FontWeight.w800, color: p.label)),
        const SizedBox(height: 8),
        Text(
          'Clubs are ranked by points. When points are level, the league’s tie-break order decides, typically:',
          style: TextStyle(fontSize: 15, color: p.label2, height: 1.4),
        ),
        const SizedBox(height: 8),
        rule('1', 'Points in matches between the tied clubs (head-to-head).'),
        rule('2', 'Goal difference in those head-to-head matches.'),
        rule('3', 'Overall goal difference.'),
        rule('4', 'Goals scored.'),
        rule('5', 'Fair-play record (fewer discipline points ranks higher).'),
        rule('6', 'Drawing of lots, always last.'),
        const SizedBox(height: 12),
        Text(
          qualificationSpots > 0
              ? 'The top $qualificationSpots qualify (above the dashed line). P played, GD goal difference, Pts points.'
              : 'P played, GD goal difference, Pts points.',
          style: TextStyle(fontSize: 13, color: p.label3, height: 1.4),
        ),
      ]),
    );
  }
}
