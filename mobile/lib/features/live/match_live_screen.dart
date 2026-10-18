import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/errors.dart';
import '../../core/format.dart';
import '../../core/session.dart';
import '../../core/theme.dart';
import '../../widgets/async_view.dart';
import '../../widgets/team_crest.dart';
import '../../widgets/ui.dart';
import 'live_feed.dart';

/// Match Live (deep link nascon://entity/match-*, QR scans). Opens for guests too: read-only score
/// over the open /ws/matches feed; signing in is offered, never required.
class MatchLiveScreen extends ConsumerWidget {
  final String matchId;
  const MatchLiveScreen({super.key, required this.matchId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final p = context.palette;
    final signedIn = ref.watch(sessionProvider) != null;
    final score = ref.watch(liveScoreProvider(matchId));
    final meta = ref.watch(liveMatchMetaProvider(matchId)).value;

    String nameFor(String side, String? id) {
      final m = meta?[side];
      if (m is Map && m['name'] != null) return '${m['name']}';
      return prettyId(id);
    }

    return Semantics(
      identifier: 'match-live-screen',
      container: true,
      label: 'Match live',
      child: FlatPage(
        title: 'Match Live',
        backFallback: signedIn ? '/fixtures' : '/login',
        onRefresh: () async => ref.invalidate(liveScoreProvider(matchId)),
        actions: signedIn
            ? [PrimaryButton(label: 'Open Full Match', icon: Icons.sports_soccer_rounded, onPressed: () => context.push('/match/$matchId'))]
            : [PrimaryButton(label: 'Sign In to Chat and Shop', icon: Icons.login_rounded, onPressed: () => context.go('/login'))],
        children: [
          score.when(
            loading: () => const Padding(padding: EdgeInsets.symmetric(vertical: 48), child: LoadingView(label: 'Connecting to the live score')),
            error: (e, _) => ErrorView(message: friendlyError(e), onRetry: () => ref.invalidate(liveScoreProvider(matchId))),
            data: (s) => Panel(
              padding: const EdgeInsets.fromLTRB(16, 20, 16, 24),
              child: Column(children: [
                MatchStatusLabel(status: s.status, fontSize: 15),
                const SizedBox(height: 18),
                Row(crossAxisAlignment: CrossAxisAlignment.center, children: [
                  _Side(teamId: s.homeId ?? 'home', name: nameFor('home', s.homeId)),
                  Semantics(
                    identifier: 'live-score',
                    label: 'Score ${s.home} to ${s.away}',
                    excludeSemantics: true,
                    child: Text('${s.home} - ${s.away}',
                        style: condensed(64, weight: FontWeight.w800, color: p.label).copyWith(fontFeatures: tabular)),
                  ),
                  _Side(teamId: s.awayId ?? 'away', name: nameFor('away', s.awayId)),
                ]),
                const SizedBox(height: 14),
                Text('Updates live. No need to refresh.', style: TextStyle(color: p.label2, fontSize: 14)),
              ]),
            ),
          ),
          const SizedBox(height: 16),
          const SectionLabel('BROADCAST'),
          Panel(
            child: Row(children: [
              Icon(Icons.live_tv_rounded, color: p.accent, size: 28),
              const SizedBox(width: 14),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(meta?['playback_url'] != null ? 'Stream is live' : 'Stream starts with the match',
                      style: condensed(20, weight: FontWeight.w700, color: p.label)),
                  const SizedBox(height: 4),
                  Text('${meta?['playback_url'] ?? 'Scan the stadium QR or open the link in a browser to watch.'}',
                      style: TextStyle(color: p.label2, fontSize: 14)),
                ]),
              ),
            ]),
          ),
          const SizedBox(height: 12),
          SecondaryButton(
            label: 'Watch the Co-Stream',
            icon: Icons.grid_view_rounded,
            onPressed: () => context.push('/costream/cs-session-101'),
          ),
          if (!signedIn) ...[
            const SizedBox(height: 16),
            Panel(
              child: Row(children: [
                Icon(Icons.visibility_rounded, color: p.label2),
                const SizedBox(width: 12),
                Expanded(child: Text('Watching as guest. Scores are live; chat and checkout need an account.', style: TextStyle(color: p.label2, fontSize: 14))),
              ]),
            ),
          ],
          if (meta?['scheduled_at'] != null) ...[
            const SizedBox(height: 16),
            ValueRow('Kick-off', formatDateTime('${meta!['scheduled_at']}')),
          ],
        ],
      ),
    );
  }
}

class _Side extends StatelessWidget {
  final String teamId;
  final String name;
  const _Side({required this.teamId, required this.name});

  @override
  Widget build(BuildContext context) => Expanded(
        child: Column(children: [
          TeamCrest(teamId: teamId, name: name, size: 56),
          const SizedBox(height: 10),
          Text(name.toUpperCase(),
              textAlign: TextAlign.center,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: condensed(16, weight: FontWeight.w700, color: context.palette.label)),
        ]),
      );
}
