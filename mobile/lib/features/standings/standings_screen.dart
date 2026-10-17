import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../data/models.dart';
import '../../data/repository.dart';
import '../../widgets/async_view.dart';
import '../../widgets/league_picker.dart';
import '../../widgets/status_chip.dart';
import '../../widgets/tenant_title.dart';

class StandingsScreen extends ConsumerWidget {
  const StandingsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      appBar: AppBar(title: const TenantTitle('Standings')),
      body: LeagueScoped(builder: (context, league) {
        final standings = ref.watch(standingsProvider(league.leagueId));
        return AsyncView<Standings>(
          value: standings,
          onRetry: () => ref.invalidate(standingsProvider(league.leagueId)),
          isEmpty: (s) => s.table.isEmpty,
          emptyMessage: 'No results yet. The table appears after the first match.',
          builder: (s) => RefreshIndicator(
            onRefresh: () => ref.refresh(standingsProvider(league.leagueId).future),
            child: ListView(children: [
              SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: DataTable(
                  showCheckboxColumn: false,
                  columnSpacing: 16,
                  columns: const [
                    DataColumn(label: Text('#'), numeric: true),
                    DataColumn(label: Text('Team')),
                    DataColumn(label: Text('P'), numeric: true, tooltip: 'Played'),
                    DataColumn(label: Text('W'), numeric: true, tooltip: 'Won'),
                    DataColumn(label: Text('D'), numeric: true, tooltip: 'Drawn'),
                    DataColumn(label: Text('L'), numeric: true, tooltip: 'Lost'),
                    DataColumn(label: Text('Diff'), numeric: true, tooltip: 'Difference'),
                    DataColumn(label: Text('Pts'), numeric: true, tooltip: 'Points'),
                    DataColumn(label: Text('Status')),
                  ],
                  rows: [
                    for (final r in s.table)
                      DataRow(
                        onSelectChanged: (_) => context.push('/club/${r.teamId}'),
                        cells: [
                          DataCell(Text('${r.rank}')),
                          DataCell(Text(r.teamName)),
                          DataCell(Text('${r.played}')),
                          DataCell(Text('${r.won}')),
                          DataCell(Text('${r.drawn}')),
                          DataCell(Text('${r.lost}')),
                          DataCell(Text('${r.diff}')),
                          DataCell(Text('${r.points}', style: const TextStyle(fontWeight: FontWeight.bold))),
                          DataCell(StatusChip.qualification(r.status)),
                        ],
                      ),
                  ],
                ),
              ),
              Padding(
                padding: const EdgeInsets.all(16),
                child: Text('Top ${s.qualificationSpots} qualify. Tap a team to see its club profile.'),
              ),
            ]),
          ),
        );
      }),
    );
  }
}
