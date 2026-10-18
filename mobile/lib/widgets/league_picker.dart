import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/models.dart';
import '../data/repository.dart';
import 'async_view.dart';
import 'ui.dart';

/// Resolves the league the user is looking at (their own, the picked one, or the first).
Future<String?> currentLeagueId(WidgetRef ref) async {
  final list = await ref.read(leaguesProvider.future);
  if (list.isEmpty) return null;
  final selected = ref.read(selectedLeagueProvider);
  return list.firstWhere((l) => l.leagueId == selected, orElse: () => list.first).leagueId;
}

/// The league currently shown (null while loading or when there are none).
League? watchCurrentLeague(WidgetRef ref) {
  final list = ref.watch(leaguesProvider).value;
  if (list == null || list.isEmpty) return null;
  final selected = ref.watch(selectedLeagueProvider);
  return list.firstWhere((l) => l.leagueId == selected, orElse: () => list.first);
}

/// Kicker text for the page title: "Alpha Premier League ’26".
String leagueKicker(League? league) {
  if (league == null) return 'League';
  final s = league.season;
  final short = RegExp(r'^\d{4}$').hasMatch(s) ? '’${s.substring(2)}' : s;
  return '${league.name} $short';
}

/// Opens the league chooser when there is more than one league (null = nothing to switch).
VoidCallback? leagueSwitcher(BuildContext context, WidgetRef ref) {
  final list = ref.watch(leaguesProvider).value ?? const <League>[];
  if (list.length < 2) return null;
  return () async {
    final current = await currentLeagueId(ref);
    if (!context.mounted) return;
    final id = await showChoiceSheet<String>(
      context,
      title: 'Choose a league',
      selected: current,
      options: [for (final l in list) (l.leagueId, '${l.name} (${l.season})')],
    );
    if (id != null) ref.read(selectedLeagueProvider.notifier).select(id);
  };
}

/// Sliver: content for the current league, with loading / empty / error states for the league list.
/// Shared by Fixtures, Standings and the Club list.
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
        return builder(context, list.firstWhere((l) => l.leagueId == selectedId, orElse: () => list.first));
      },
    );
  }
}
