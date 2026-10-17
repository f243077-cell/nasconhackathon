import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/format.dart';
import '../../core/session.dart';
import '../../data/models.dart';
import '../../data/repository.dart';
import '../../widgets/async_view.dart';
import '../../widgets/status_chip.dart';

/// Live score (largest text in the app), event timeline, pinned product.
class MatchScreen extends ConsumerWidget {
  final String matchId;
  const MatchScreen({super.key, required this.matchId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // Real-time: refetch when the WebSocket says this match changed.
    ref.listen(liveUpdatesProvider, (_, next) {
      if (next.value?['match_id'] == matchId) ref.invalidate(matchProvider(matchId));
    });
    final session = ref.watch(sessionProvider);
    final match = ref.watch(matchProvider(matchId));

    return Scaffold(
      appBar: AppBar(title: const Text('Match')),
      body: AsyncView<MatchDetail>(
        value: match,
        onRetry: () => ref.invalidate(matchProvider(matchId)),
        builder: (m) => RefreshIndicator(
          onRefresh: () => ref.refresh(matchProvider(matchId).future),
          child: ListView(padding: const EdgeInsets.only(bottom: 24), children: [
            ScoreBoard(match: m),
            if (session?.canScore ?? false)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: OutlinedButton.icon(
                  onPressed: () => context.push('/scoring?match=${m.matchId}'),
                  icon: const Icon(Icons.add),
                  label: const Text('Add score event'),
                ),
              ),
            const SectionHeader('Featured product'),
            if (m.pinnedProduct != null)
              PinnedProductCard(product: m.pinnedProduct!)
            else
              const Padding(padding: EdgeInsets.symmetric(horizontal: 16), child: Text('No product pinned for this match.')),
            if (session?.canPinProduct ?? false)
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
                child: OutlinedButton.icon(
                  onPressed: () => _pickProductToPin(context, ref, m.matchId),
                  icon: const Icon(Icons.push_pin),
                  label: const Text('Pin a product'),
                ),
              ),
            const SectionHeader('Timeline'),
            if (m.events.isEmpty)
              const Padding(padding: EdgeInsets.symmetric(horizontal: 16), child: Text('No events yet.'))
            else
              for (final e in m.events.reversed) EventTile(event: e, match: m),
          ]),
        ),
      ),
    );
  }

  Future<void> _pickProductToPin(BuildContext context, WidgetRef ref, String matchId) async {
    final products = await ref.read(productsProvider.future);
    if (!context.mounted) return;
    final chosen = await showModalBottomSheet<Product>(
      context: context,
      builder: (ctx) => SafeArea(
        child: ListView(shrinkWrap: true, children: [
          const ListTile(title: Text('Pin which product?')),
          for (final p in products) ListTile(title: Text(p.name), onTap: () => Navigator.pop(ctx, p)),
        ]),
      ),
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

class ScoreBoard extends StatelessWidget {
  final MatchDetail match;
  const ScoreBoard({super.key, required this.match});

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    Widget side(TeamScore s) => Expanded(
          child: Column(children: [
            Text(s.name, textAlign: TextAlign.center, style: t.titleMedium, maxLines: 2, overflow: TextOverflow.ellipsis),
            const SizedBox(height: 8),
            FittedBox(child: Text(s.display, style: t.displayLarge?.copyWith(fontWeight: FontWeight.bold))),
          ]),
        );
    return Card(
      margin: const EdgeInsets.all(16),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(children: [
          StatusChip.match(match.status),
          const SizedBox(height: 12),
          Semantics(
            label: '${match.home.name} ${match.home.display}, ${match.away.name} ${match.away.display}',
            excludeSemantics: true,
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              side(match.home),
              Padding(padding: const EdgeInsets.only(top: 40), child: Text('–', style: t.headlineMedium)),
              side(match.away),
            ]),
          ),
          if (match.status == 'completed') ...[
            const SizedBox(height: 8),
            Text(match.outcome == 'draw' ? 'Draw' : 'Winner: ${match.teamName(match.winnerTeamId)}'),
          ],
        ]),
      ),
    );
  }
}

class EventTile extends StatelessWidget {
  final MatchEvent event;
  final MatchDetail match;
  final Widget? trailing;
  const EventTile({super.key, required this.event, required this.match, this.trailing});

  @override
  Widget build(BuildContext context) {
    final e = event;
    final team = e.payload['team_id'] == null ? null : match.teamName(e.payload['team_id']);
    final title = switch (e.type) {
      'score' => '${humanize(e.payload['event_type'] ?? 'score')} · $team',
      'compensation' => 'Correction: ${e.payload['reason'] ?? ''}',
      'discipline' => 'Discipline (${e.payload['points']}) · $team',
      _ => humanize(e.type),
    };
    return ListTile(
      leading: CircleAvatar(child: Text('${e.sequence}')),
      title: Text(title, style: e.compensated ? const TextStyle(decoration: TextDecoration.lineThrough) : null),
      subtitle: e.compensated ? const Text('Corrected') : null,
      trailing: trailing,
    );
  }
}

class PinnedProductCard extends StatelessWidget {
  final Product product;
  const PinnedProductCard({super.key, required this.product});

  @override
  Widget build(BuildContext context) => Card(
        margin: const EdgeInsets.symmetric(horizontal: 16),
        child: ListTile(
          leading: const Icon(Icons.shopping_bag, semanticLabel: 'Product'),
          title: Text(product.name),
          subtitle: Text('From ${formatMoney(product.fromPriceMinor)}'),
          trailing: FilledButton(onPressed: () => context.push('/product/${product.productId}'), child: const Text('Buy')),
        ),
      );
}
