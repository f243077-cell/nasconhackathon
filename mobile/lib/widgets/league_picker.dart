import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/models.dart';
import '../data/repository.dart';
import 'async_view.dart';

/// League dropdown on top + content for the chosen league below.
/// Shared by Fixtures, Standings, the Club list and Scoring.
class LeagueScoped extends ConsumerWidget {
  final Widget Function(BuildContext context, League league) builder;
  const LeagueScoped({super.key, required this.builder});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final leagues = ref.watch(leaguesProvider);
    return AsyncView<List<League>>(
      value: leagues,
      onRetry: () => ref.invalidate(leaguesProvider),
      isEmpty: (l) => l.isEmpty,
      emptyMessage: 'No leagues yet',
      builder: (list) {
        final selectedId = ref.watch(selectedLeagueProvider);
        final league = list.firstWhere((l) => l.leagueId == selectedId, orElse: () => list.first);
        return Column(children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
            child: DropdownButtonFormField<String>(
              key: ValueKey(league.leagueId),
              initialValue: league.leagueId,
              isExpanded: true,
              decoration: const InputDecoration(labelText: 'League'),
              items: [
                for (final l in list)
                  DropdownMenuItem(value: l.leagueId, child: Text('${l.name} (${l.season})', overflow: TextOverflow.ellipsis)),
              ],
              onChanged: (id) => id == null ? null : ref.read(selectedLeagueProvider.notifier).select(id),
            ),
          ),
          Expanded(child: builder(context, league)),
        ]);
      },
    );
  }
}
