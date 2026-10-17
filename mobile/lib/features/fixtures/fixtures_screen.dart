import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/format.dart';
import '../../data/models.dart';
import '../../data/repository.dart';
import '../../widgets/async_view.dart';
import '../../widgets/league_picker.dart';
import '../../widgets/status_chip.dart';
import '../../widgets/tenant_title.dart';

class FixturesScreen extends ConsumerWidget {
  const FixturesScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      appBar: AppBar(title: const TenantTitle('Fixtures')),
      body: LeagueScoped(builder: (context, league) {
        final fixtures = ref.watch(fixturesProvider(league.leagueId));
        return AsyncView<List<Fixture>>(
          value: fixtures,
          onRetry: () => ref.invalidate(fixturesProvider(league.leagueId)),
          isEmpty: (l) => l.isEmpty,
          emptyMessage: 'No matches yet',
          builder: (list) => RefreshIndicator(
            onRefresh: () => ref.refresh(fixturesProvider(league.leagueId).future),
            child: ListView.builder(
              padding: const EdgeInsets.all(8),
              itemCount: list.length,
              itemBuilder: (_, i) => MatchCard(fixture: list[i]),
            ),
          ),
        );
      }),
    );
  }
}

class MatchCard extends StatelessWidget {
  final Fixture fixture;
  const MatchCard({super.key, required this.fixture});

  @override
  Widget build(BuildContext context) {
    final f = fixture;
    return Card(
      child: ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        title: Text('${f.homeName}  vs  ${f.awayName}', style: Theme.of(context).textTheme.titleMedium),
        subtitle: Text([formatDateTime(f.scheduledAt), if (f.venue != null) f.venue!].join(' · ')),
        trailing: StatusChip.match(f.status),
        onTap: () => context.push('/match/${f.matchId}'),
      ),
    );
  }
}
