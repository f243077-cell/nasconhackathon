import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/theme.dart';
import '../data/models.dart';
import '../data/repository.dart';
import 'async_view.dart';

/// Resolves the league the user is looking at (their own, the picked one, or the first).
Future<String?> currentLeagueId(WidgetRef ref) async {
  final list = await ref.read(leaguesProvider.future);
  if (list.isEmpty) return null;
  final selected = ref.read(selectedLeagueProvider);
  return list.firstWhere((l) => l.leagueId == selected, orElse: () => list.first).leagueId;
}

/// Sliver: league switcher under the large title, then content for that league.
/// Shared by Fixtures, Standings, the Club list and Scoring.
class LeagueScoped extends ConsumerWidget {
  final Widget Function(BuildContext context, League league) builder; // returns a sliver
  const LeagueScoped({super.key, required this.builder});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final leagues = ref.watch(leaguesProvider);
    return AsyncSliver<List<League>>(
      value: leagues,
      onRetry: () => ref.invalidate(leaguesProvider),
      isEmpty: (l) => l.isEmpty,
      emptyMessage: 'No leagues yet',
      emptyIcon: Icons.emoji_events_rounded,
      builder: (list) {
        final selectedId = ref.watch(selectedLeagueProvider);
        final league = list.firstWhere((l) => l.leagueId == selectedId, orElse: () => list.first);
        return SliverMainAxisGroup(slivers: [
          SliverToBoxAdapter(child: LeagueSwitcher(league: league, leagues: list)),
          builder(context, league),
        ]);
      },
    );
  }
}

/// "Premier Football League · 2026 ⌄" — opens an action sheet to switch league.
class LeagueSwitcher extends ConsumerWidget {
  final League league;
  final List<League> leagues;
  const LeagueSwitcher({super.key, required this.league, required this.leagues});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final p = context.palette;
    final t = Theme.of(context).textTheme;
    final canSwitch = leagues.length > 1;
    return Padding(
      padding: const EdgeInsets.fromLTRB(8, 4, 16, 16),
      child: Align(
        alignment: Alignment.centerLeft,
        child: TextButton(
          onPressed: canSwitch ? () => _choose(context, ref) : null,
          style: TextButton.styleFrom(padding: const EdgeInsets.symmetric(horizontal: 8)),
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            Flexible(
              child: Text(
                '${league.name}, ${league.season}',
                overflow: TextOverflow.ellipsis,
                style: t.bodyLarge!.copyWith(color: canSwitch ? p.accent : p.secondaryLabel, fontWeight: FontWeight.w500),
              ),
            ),
            if (canSwitch) ...[
              const SizedBox(width: 4),
              Icon(Icons.keyboard_arrow_down_rounded, size: 20, color: p.accent, semanticLabel: 'Change league'),
            ],
          ]),
        ),
      ),
    );
  }

  Future<void> _choose(BuildContext context, WidgetRef ref) async {
    final id = await showCupertinoModalPopup<String>(
      context: context,
      builder: (ctx) => CupertinoActionSheet(
        title: const Text('Choose a League'),
        actions: [
          for (final l in leagues)
            CupertinoActionSheetAction(
              isDefaultAction: l.leagueId == league.leagueId,
              onPressed: () => Navigator.pop(ctx, l.leagueId),
              child: Text('${l.name} (${l.season})', overflow: TextOverflow.ellipsis),
            ),
        ],
        cancelButton: CupertinoActionSheetAction(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
      ),
    );
    if (id != null) ref.read(selectedLeagueProvider.notifier).select(id);
  }
}
