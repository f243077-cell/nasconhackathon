import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/format.dart';
import '../../core/theme.dart';
import '../../data/models.dart';
import '../../data/repository.dart';
import '../../widgets/async_view.dart';
import '../../widgets/league_picker.dart';
import '../../widgets/status_chip.dart';
import '../../widgets/tenant_title.dart';
import '../../widgets/ui.dart';

/// Fixtures grouped by what matters now: Live, then Upcoming, then Results.
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
                  if (items.isNotEmpty) Section(header: title, children: [for (final f in items) MatchRow(fixture: f)]),
              ]);
            },
          );
        }),
      ],
    );
  }
}

/// Two stacked team names on the left, status and kick-off on the right.
class MatchRow extends StatelessWidget {
  final Fixture fixture;
  const MatchRow({super.key, required this.fixture});

  @override
  Widget build(BuildContext context) {
    final f = fixture;
    final t = Theme.of(context).textTheme;
    final p = context.palette;
    return Semantics(
      button: true,
      label: '${f.homeName} versus ${f.awayName}, ${formatDateTime(f.scheduledAt)}',
      child: InkWell(
        onTap: () => context.push('/match/${f.matchId}'),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 8, 12),
          child: Row(children: [
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(f.homeName, style: t.bodyLarge, overflow: TextOverflow.ellipsis),
                const SizedBox(height: 2),
                Text(f.awayName, style: t.bodyLarge, overflow: TextOverflow.ellipsis),
                const SizedBox(height: 6),
                Text(
                  [formatDateTime(f.scheduledAt), if (f.venue != null) f.venue!].join(', '),
                  style: t.bodySmall,
                  overflow: TextOverflow.ellipsis,
                ),
              ]),
            ),
            const SizedBox(width: 12),
            StatusChip.match(f.status),
            Icon(Icons.chevron_right_rounded, color: p.secondaryLabel.withValues(alpha: 0.6)),
          ]),
        ),
      ),
    );
  }
}
