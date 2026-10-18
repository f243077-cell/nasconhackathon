import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/format.dart';
import '../../core/session.dart';
import '../../core/theme.dart';
import '../../data/models.dart';
import '../../data/repository.dart';
import '../../widgets/async_view.dart';
import '../../widgets/player_card.dart';
import '../../widgets/sync_status_bar.dart';
import '../../widgets/team_crest.dart';
import '../../widgets/ui.dart';

/// The app's signature screen: the home side's colour behind one huge score, then the match
/// told three ways (timeline, lineups, stats). A pinned product floats at the bottom.
class MatchScreen extends ConsumerStatefulWidget {
  final String matchId;
  const MatchScreen({super.key, required this.matchId});

  @override
  ConsumerState<MatchScreen> createState() => _MatchScreenState();
}

class _MatchScreenState extends ConsumerState<MatchScreen> {
  int _tab = 0;

  @override
  Widget build(BuildContext context) {
    final matchId = widget.matchId;
    // Real-time: refetch when the WebSocket says this match changed.
    ref.listen(liveUpdatesProvider, (_, next) {
      if (next.value?['match_id'] == matchId) ref.invalidate(matchProvider(matchId));
    });
    final session = ref.watch(sessionProvider);
    final match = ref.watch(matchProvider(matchId));
    final m = match.value;

    return Scaffold(
      bottomNavigationBar: m?.pinnedProduct == null ? null : PinnedProductBar(product: m!.pinnedProduct!),
      body: AsyncView<MatchDetail>(
        value: match,
        onRetry: () => ref.invalidate(matchProvider(matchId)),
        builder: (m) => RefreshIndicator(
          onRefresh: () => ref.refresh(matchProvider(matchId).future),
          color: context.palette.onAccent,
          backgroundColor: context.palette.accent,
          child: ListView(padding: const EdgeInsets.only(bottom: 32), children: [
            ScoreHero(match: m),
            UnderlineTabs(labels: const ['Timeline', 'Lineups', 'Stats'], index: _tab, onChanged: (i) => setState(() => _tab = i)),
            if ((session?.canScore ?? false) || (session?.canPinProduct ?? false))
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 16, 20, 0),
                child: Row(children: [
                  if (session?.canScore ?? false)
                    Expanded(
                      child: SecondaryButton(
                        label: 'Score entry',
                        icon: Icons.scoreboard_outlined,
                        height: 48,
                        onPressed: () => context.push('/scoring?match=${m.matchId}'),
                      ),
                    ),
                  if ((session?.canScore ?? false) && (session?.canPinProduct ?? false)) const SizedBox(width: 10),
                  if (session?.canPinProduct ?? false)
                    Expanded(
                      child: SecondaryButton(
                        label: m.pinnedProduct == null ? 'Pin product' : 'Change pin',
                        icon: Icons.push_pin_outlined,
                        height: 48,
                        onPressed: () => _pickProductToPin(context, m.matchId),
                      ),
                    ),
                ]),
              ),
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 6, 20, 0),
              child: SmoothSwitch(
                switchKey: _tab,
                child: switch (_tab) {
                  0 => MatchTimeline(match: m),
                  1 => _Lineups(match: m),
                  _ => _Stats(match: m),
                },
              ),
            ),
          ]),
        ),
      ),
    );
  }

  Future<void> _pickProductToPin(BuildContext context, String matchId) async {
    final products = await ref.read(productsProvider.future);
    if (!context.mounted) return;
    final chosen = await showChoiceSheet<Product>(
      context,
      title: 'Pin a product',
      message: 'Fans watching this match will see it.',
      options: [for (final p in products) (p, '${p.name} · ${formatMoney(p.fromPriceMinor)}')],
    );
    if (chosen == null) return;
    try {
      await ref.read(repositoryProvider).pinProduct(matchId, chosen.productId);
      ref.invalidate(matchProvider(matchId));
      if (context.mounted) showSuccess(context, '${chosen.name} pinned.');
    } catch (e) {
      if (context.mounted) showError(context, e);
    }
  }
}

/// Home colour fading into the night, status badge, crests either side of the score.
class ScoreHero extends StatelessWidget {
  final MatchDetail match;
  const ScoreHero({super.key, required this.match});

  @override
  Widget build(BuildContext context) {
    final m = match;
    final p = context.palette;
    final t = Theme.of(context).textTheme;
    final completed = m.status == 'completed';
    final homeColor = TeamCrest.colorFor(m.home.teamId);

    final badge = switch (m.status) {
      'in_progress' => Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
          decoration: BoxDecoration(color: p.liveFill, borderRadius: BorderRadius.circular(12)),
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            const LiveDot(color: Colors.white, size: 7),
            const SizedBox(width: 6),
            Text('LIVE', style: condensed(13, weight: FontWeight.w700, tracking: 1, color: Colors.white)),
          ]),
        ),
      'completed' => Tag('Full time', color: p.label2, outlined: true, fontSize: 13),
      'upcoming' => Tag('Kick-off ${formatDateTime(m.scheduledAt)}', color: p.label2, outlined: true, fontSize: 13),
      _ => Tag(humanize(m.status), color: p.warning, outlined: true, fontSize: 13),
    };

    Widget side(TeamScore s) {
      final won = completed && m.winnerTeamId == s.teamId;
      return Expanded(
        child: Column(children: [
          TeamCrest(teamId: s.teamId, name: s.name, size: 56),
          const SizedBox(height: 8),
          Text(
            s.name.toUpperCase(),
            maxLines: 2,
            textAlign: TextAlign.center,
            style: condensed(16, weight: FontWeight.w700, color: completed && !won ? p.label2 : p.label, height: 1.05),
          ),
        ]),
      );
    }

    final details = [
      ?m.venue,
      if (m.status != 'upcoming' && m.scheduledAt != null) formatDateTime(m.scheduledAt),
      if (completed) m.outcome == 'draw' ? 'Draw' : '${m.teamName(m.winnerTeamId)} won',
    ].join(' · ');

    return Semantics(
      container: true,
      label: '${m.home.name} ${m.home.display}, ${m.away.name} ${m.away.display}. ${humanize(m.status)}.',
      child: DecoratedBox(
        decoration: BoxDecoration(
          gradient: LinearGradient(begin: Alignment.topCenter, end: Alignment.bottomCenter, colors: [homeColor, p.canvas]),
        ),
        child: SafeArea(
          bottom: false,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 4, 20, 24),
            child: Column(children: [
              const ScreenHeader(leading: BackChip(filled: true), trailing: StatusPill()),
              const SizedBox(height: 10),
              badge,
              const SizedBox(height: 16),
              Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
                side(m.home),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 6),
                  child: ExcludeSemantics(
                    child: FittedBox(
                      fit: BoxFit.scaleDown,
                      child: _AnimatedScore(
                        text: m.status == 'upcoming' ? 'VS' : '${m.home.display}–${m.away.display}',
                        style: m.status == 'upcoming' ? t.displayLarge!.copyWith(fontSize: 56, color: p.label2) : t.displayLarge!,
                      ),
                    ),
                  ),
                ),
                side(m.away),
              ]),
              if (details.isNotEmpty) ...[
                const SizedBox(height: 14),
                Text(details, textAlign: TextAlign.center, style: const TextStyle(fontSize: 13, color: Color(0xFFC9C9BF))),
              ],
            ]),
          ),
        ),
      ),
    );
  }
}

/// Score digits roll up when they change (the one orchestrated moment). Off under reduced motion.
class _AnimatedScore extends StatelessWidget {
  final String text;
  final TextStyle style;
  const _AnimatedScore({required this.text, required this.style});

  @override
  Widget build(BuildContext context) {
    final reduce = MediaQuery.of(context).disableAnimations;
    return AnimatedSwitcher(
      duration: reduce ? Duration.zero : const Duration(milliseconds: 280),
      switchInCurve: Curves.easeOutCubic,
      switchOutCurve: Curves.easeInCubic,
      transitionBuilder: (child, animation) => FadeTransition(
        opacity: animation,
        child: SlideTransition(position: Tween(begin: const Offset(0, 0.35), end: Offset.zero).animate(animation), child: child),
      ),
      child: Text(text, key: ValueKey(text), maxLines: 1, style: style),
    );
  }
}

/// Player names for both squads (for "GOAL Hamza R." lines). Empty until the clubs load.
Map<String, String> _playerNames(WidgetRef ref, MatchDetail m) => {
      for (final id in [m.home.teamId, m.away.teamId])
        for (final pl in ref.watch(clubProvider(id)).value?.roster ?? const <RosterPlayer>[]) pl.playerId: pl.name,
    };

/// One line per event, newest first. Corrected events are struck through with the correction's reason.
class MatchTimeline extends ConsumerWidget {
  final MatchDetail match;
  final int? limit;
  const MatchTimeline({super.key, required this.match, this.limit});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final m = match;
    final p = context.palette;
    final names = _playerNames(ref, m);
    final reasons = {
      for (final e in m.events)
        if (e.type == 'compensation') '${e.payload['compensates']}': '${e.payload['reason'] ?? 'Correction'}',
    };
    var rows = m.events.where((e) => e.type != 'compensation' && e.type != 'match_init').toList().reversed.toList();
    if (limit != null) rows = rows.take(limit!).toList();
    if (rows.isEmpty) {
      return const Padding(padding: EdgeInsets.only(top: 24), child: EmptyState(message: 'No events yet', icon: Icons.timer_outlined));
    }

    return Column(children: [
      for (var i = 0; i < rows.length; i++)
        Builder(builder: (context) {
          final e = rows[i];
          final teamId = e.payload['team_id'] as String?;
          final team = teamId == null ? null : initialsOf(m.teamName(teamId));
          final player = names[e.payload['player_id']];
          final minute = e.payload['minute'];
          final (title, accent) = switch (e.type) {
            'score' => (humanize('${e.payload['event_type'] ?? 'score'}').toUpperCase(), true),
            'discipline' => ('CARD · ${e.payload['points']} PTS', false),
            'tiebreak_winner' => ('TIEBREAK WON', true),
            'match_start' => ('KICK-OFF', false),
            'match_end' => ('FULL TIME', false),
            _ => (humanize(e.type).toUpperCase(), false),
          };
          final struck = e.compensated;
          final lead = minute is num ? '$minute′' : '#${e.sequence}';
          return Container(
            padding: const EdgeInsets.symmetric(vertical: 11),
            decoration: BoxDecoration(border: i == rows.length - 1 ? null : Border(bottom: BorderSide(color: p.hairline))),
            child: Row(children: [
              SizedBox(
                width: 48,
                child: Text(lead, style: condensed(20, weight: FontWeight.w700, color: accent && !struck ? p.accent : p.label3)),
              ),
              const SizedBox(width: 6),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text.rich(
                    TextSpan(children: [
                      TextSpan(text: title, style: const TextStyle(fontWeight: FontWeight.w700)),
                      if (player != null) TextSpan(text: ' ${shortName(player)}'),
                      if (team != null) TextSpan(text: ' $team', style: TextStyle(color: p.label3)),
                    ]),
                    style: TextStyle(
                      fontSize: 15,
                      color: struck ? p.label3 : p.label,
                      decoration: struck ? TextDecoration.lineThrough : null,
                      decorationColor: p.label3,
                    ),
                  ),
                  if (struck)
                    Padding(
                      padding: const EdgeInsets.only(top: 2),
                      child: Text('↺ Overturned — ${reasons[e.eventId] ?? 'corrected'}', style: TextStyle(fontSize: 13, color: p.warning)),
                    ),
                ]),
              ),
            ]),
          );
        }),
    ]);
  }
}

class _Lineups extends ConsumerWidget {
  final MatchDetail match;
  const _Lineups({required this.match});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    Widget squad(TeamScore s) {
      final club = ref.watch(clubProvider(s.teamId));
      return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Padding(
          padding: const EdgeInsets.only(top: 16, bottom: 6),
          child: Row(children: [
            TeamCrest(teamId: s.teamId, name: s.name, size: 20),
            const SizedBox(width: 8),
            Expanded(child: SectionLabel(s.name, padding: EdgeInsets.zero)),
          ]),
        ),
        club.when(
          loading: () => const Padding(padding: EdgeInsets.all(16), child: LoadingView()),
          error: (_, _) => Text('Squad not available offline.', style: TextStyle(color: context.palette.label3)),
          data: (c) => c.roster.isEmpty
              ? Text('No players registered.', style: TextStyle(color: context.palette.label3))
              : Column(children: [for (final pl in c.roster) SquadRow(player: pl, clubId: c.clubId, dense: true)]),
        ),
      ]);
    }

    return Column(children: [squad(match.home), squad(match.away)]);
  }
}

/// Head-to-head numbers from the event log: score, each scoring type, discipline, fair play.
class _Stats extends StatelessWidget {
  final MatchDetail match;
  const _Stats({required this.match});

  @override
  Widget build(BuildContext context) {
    final m = match;
    final p = context.palette;
    final live = m.events.where((e) => !e.compensated);
    int count(String team, bool Function(MatchEvent) test) => live.where((e) => e.payload['team_id'] == team && test(e)).length;
    final types = {for (final e in live) if (e.type == 'score') '${e.payload['event_type']}'};
    final rows = <(String, num, num)>[
      ('Score', m.home.score, m.away.score),
      for (final ty in types)
        (humanize(ty), count(m.home.teamId, (e) => e.type == 'score' && e.payload['event_type'] == ty),
            count(m.away.teamId, (e) => e.type == 'score' && e.payload['event_type'] == ty)),
      ('Cards', count(m.home.teamId, (e) => e.type == 'discipline'), count(m.away.teamId, (e) => e.type == 'discipline')),
      ('Fair play points', m.home.fairPlay, m.away.fairPlay),
    ];

    Widget bar(num a, num b, bool home) {
      final total = (a + b) == 0 ? 1 : a + b;
      final frac = (home ? a : b) / total;
      return Expanded(
        child: Align(
          alignment: home ? Alignment.centerRight : Alignment.centerLeft,
          child: FractionallySizedBox(
            widthFactor: frac.clamp(0.02, 1).toDouble(),
            child: Container(height: 4, decoration: BoxDecoration(color: home ? p.accent : p.label2, borderRadius: BorderRadius.circular(2))),
          ),
        ),
      );
    }

    return Column(children: [
      Padding(
        padding: const EdgeInsets.only(top: 16, bottom: 4),
        child: Row(children: [
          TeamCrest(teamId: m.home.teamId, name: m.home.name, size: 22),
          const Spacer(),
          TeamCrest(teamId: m.away.teamId, name: m.away.name, size: 22),
        ]),
      ),
      for (final (label, a, b) in rows)
        Semantics(
          label: '$label: ${m.home.name} $a, ${m.away.name} $b',
          excludeSemantics: true,
          child: Container(
            padding: const EdgeInsets.symmetric(vertical: 12),
            decoration: BoxDecoration(border: Border(bottom: BorderSide(color: p.hairline))),
            child: Column(children: [
              Row(children: [
                Text('$a', style: condensed(22, weight: FontWeight.w800, color: p.label)),
                Expanded(child: Text(label.toUpperCase(), textAlign: TextAlign.center, style: condensed(13, weight: FontWeight.w600, tracking: 1, color: p.label3))),
                Text('$b', style: condensed(22, weight: FontWeight.w800, color: p.label)),
              ]),
              const SizedBox(height: 6),
              Row(children: [bar(a, b, true), const SizedBox(width: 6), bar(a, b, false)]),
            ]),
          ),
        ),
    ]);
  }
}

/// The light "pinned" card that floats over the bottom of the match screen.
class PinnedProductBar extends StatelessWidget {
  final Product product;
  const PinnedProductBar({super.key, required this.product});

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    return SafeArea(
      top: false,
      minimum: const EdgeInsets.only(bottom: 14),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12),
        child: Container(
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(
            color: p.label,
            borderRadius: BorderRadius.circular(16),
            boxShadow: const [BoxShadow(color: Color(0x80000000), blurRadius: 30, offset: Offset(0, 12))],
          ),
          child: Row(children: [
            ClipRRect(
              borderRadius: BorderRadius.circular(10),
              child: SizedBox.square(dimension: 52, child: ProductArtwork(type: product.type, imageUrl: product.imageUrl, iconSize: 24)),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
                Text('PINNED FOR THIS MATCH', style: condensed(11, weight: FontWeight.w600, tracking: 1, color: const Color(0xFF55554E))),
                Text(
                  '${product.name} · ${formatMoney(product.fromPriceMinor)}',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700, color: p.canvas),
                ),
              ]),
            ),
            const SizedBox(width: 8),
            Semantics(
              button: true,
              label: 'Buy ${product.name}',
              excludeSemantics: true,
              child: Material(
                color: p.canvas,
                borderRadius: BorderRadius.circular(12),
                child: InkWell(
                  borderRadius: BorderRadius.circular(12),
                  onTap: () => context.push('/product/${product.productId}'),
                  child: SizedBox(
                    height: 48,
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 18),
                      child: Center(child: Text('BUY', style: condensed(16, weight: FontWeight.w700, tracking: 1, color: p.accent))),
                    ),
                  ),
                ),
              ),
            ),
          ]),
        ),
      ),
    );
  }
}
