import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/format.dart';
import '../../core/session.dart';
import '../../core/theme.dart';
import '../../data/models.dart';
import '../../data/repository.dart';
import '../../widgets/async_view.dart';
import '../../widgets/team_crest.dart';
import '../../widgets/ui.dart';

/// The app's signature screen: one huge live score, then the story of the match.
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
        builder: (m) => RefreshIndicator.adaptive(
          onRefresh: () => ref.refresh(matchProvider(matchId).future),
          child: ListView(padding: const EdgeInsets.only(bottom: 32), children: [
            ScoreBoard(match: m),
            if (session?.canScore ?? false)
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 28),
                child: SecondaryButton(
                  label: 'Add Score Event',
                  icon: Icons.add_rounded,
                  onPressed: () => context.push('/scoring?match=${m.matchId}'),
                ),
              ),
            if (m.pinnedProduct != null || (session?.canPinProduct ?? false))
              Section(
                header: 'Featured',
                children: [
                  if (m.pinnedProduct != null) PinnedProductRow(product: m.pinnedProduct!),
                  if (session?.canPinProduct ?? false)
                    ListTile(
                      leading: const Icon(Icons.push_pin_rounded),
                      title: Text(m.pinnedProduct == null ? 'Pin a Product' : 'Change Pinned Product',
                          style: TextStyle(color: context.palette.accent)),
                      onTap: () => _pickProductToPin(context, ref, m.matchId),
                    ),
                ],
              ),
            if (m.events.isEmpty)
              const Section(header: 'Timeline', children: [ListTile(title: Text('No events yet'))])
            else
              Section(
                header: 'Timeline',
                dividerIndent: 60,
                children: [for (final e in m.events.reversed) EventTile(event: e, match: m)],
              ),
          ]),
        ),
      ),
    );
  }

  Future<void> _pickProductToPin(BuildContext context, WidgetRef ref, String matchId) async {
    final products = await ref.read(productsProvider.future);
    if (!context.mounted) return;
    final chosen = await showCupertinoModalPopup<Product>(
      context: context,
      builder: (ctx) => CupertinoActionSheet(
        title: const Text('Pin a Product'),
        message: const Text('Fans watching this match will see it.'),
        actions: [
          for (final p in products)
            CupertinoActionSheetAction(onPressed: () => Navigator.pop(ctx, p), child: Text(p.name)),
        ],
        cancelButton: CupertinoActionSheetAction(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
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
  final bool compact;
  const ScoreBoard({super.key, required this.match, this.compact = false});

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final p = context.palette;
    final scoreStyle = (compact ? t.headlineMedium!.copyWith(fontSize: 44) : t.displayLarge)!.copyWith(fontFeatures: tabular);
    final completed = match.status == 'completed';

    Widget team(TeamScore s, CrossAxisAlignment align) {
      final won = completed && match.winnerTeamId == s.teamId;
      return Expanded(
        child: Column(crossAxisAlignment: align, children: [
          TeamCrest(teamId: s.teamId, name: s.name, size: compact ? 36 : 56),
          const SizedBox(height: 10),
          Text(
            s.name,
            textAlign: align == CrossAxisAlignment.start ? TextAlign.start : TextAlign.end,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: (won ? t.titleMedium : t.bodyLarge)!.copyWith(color: won ? p.label : p.secondaryLabel),
          ),
          const SizedBox(height: 4),
          FittedBox(fit: BoxFit.scaleDown, child: _AnimatedScore(text: s.display, style: scoreStyle)),
        ]),
      );
    }

    return Semantics(
      label: '${match.home.name} ${match.home.display}, ${match.away.name} ${match.away.display}. '
          '${completed ? (match.outcome == 'draw' ? 'Draw' : 'Winner ${match.teamName(match.winnerTeamId)}') : ''}',
      excludeSemantics: true,
      child: Padding(
        padding: EdgeInsets.fromLTRB(24, compact ? 8 : 20, 24, compact ? 20 : 32),
        child: Column(children: [
          MatchStatusLabel(status: match.status, large: true),
          SizedBox(height: compact ? 12 : 20),
          Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
            team(match.home, CrossAxisAlignment.start),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12),
              child: Text('–', style: scoreStyle.copyWith(color: p.secondaryLabel.withValues(alpha: 0.5), fontWeight: FontWeight.w300)),
            ),
            team(match.away, CrossAxisAlignment.end),
          ]),
          if (completed) ...[
            const SizedBox(height: 12),
            Text(
              match.outcome == 'draw' ? 'Draw' : '${match.teamName(match.winnerTeamId)} won',
              style: t.bodyMedium,
            ),
          ],
        ]),
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
        child: SlideTransition(
          position: Tween(begin: const Offset(0, 0.35), end: Offset.zero).animate(animation),
          child: child,
        ),
      ),
      child: Text(text, key: ValueKey(text), style: style),
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
    final p = context.palette;
    final t = Theme.of(context).textTheme;
    final team = e.payload['team_id'] == null ? null : match.teamName(e.payload['team_id']);
    final (icon, title) = switch (e.type) {
      'score' => (Icons.sports_soccer_rounded, humanize(e.payload['event_type'] ?? 'score')),
      'compensation' => (Icons.undo_rounded, 'Correction'),
      'discipline' => (Icons.style_rounded, 'Discipline (${e.payload['points']})'),
      'match_start' => (Icons.play_arrow_rounded, 'Kick-off'),
      'match_end' => (Icons.flag_rounded, 'Full time'),
      'match_init' => (Icons.event_rounded, 'Match created'),
      _ => (Icons.circle_outlined, humanize(e.type)),
    };
    final subtitle = [
      ?team,
      if (e.type == 'compensation' && (e.payload['reason'] ?? '').toString().isNotEmpty) '${e.payload['reason']}',
      if (e.compensated) 'Corrected',
    ].join(', ');
    return ListTile(
      leading: SizedBox(
        width: 28,
        child: Text('${e.sequence}', textAlign: TextAlign.center, style: t.bodySmall!.copyWith(fontFeatures: tabular)),
      ),
      horizontalTitleGap: 16,
      title: Row(children: [
        Icon(icon, size: 18, color: e.compensated ? p.secondaryLabel : p.accent),
        const SizedBox(width: 8),
        Flexible(
          child: Text(
            title,
            overflow: TextOverflow.ellipsis,
            style: e.compensated ? TextStyle(decoration: TextDecoration.lineThrough, color: p.secondaryLabel) : null,
          ),
        ),
      ]),
      subtitle: subtitle.isEmpty ? null : Text(subtitle),
      trailing: trailing,
    );
  }
}

class PinnedProductRow extends StatelessWidget {
  final Product product;
  const PinnedProductRow({super.key, required this.product});

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Padding(
      padding: const EdgeInsets.all(12),
      child: Row(children: [
        ClipRRect(
          borderRadius: BorderRadius.circular(10),
          child: SizedBox.square(dimension: 56, child: ProductArtwork(type: product.type, iconSize: 26)),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(product.name, style: t.titleMedium, overflow: TextOverflow.ellipsis),
            Text('From ${formatMoney(product.fromPriceMinor)}', style: t.bodyMedium),
          ]),
        ),
        FilledButton(
          style: FilledButton.styleFrom(minimumSize: const Size(72, 40), shape: const StadiumBorder()),
          onPressed: () => context.push('/product/${product.productId}'),
          child: const Text('Buy'),
        ),
      ]),
    );
  }
}
