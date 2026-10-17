import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:uuid/uuid.dart';

import '../../core/format.dart';
import '../../core/session.dart';
import '../../data/models.dart';
import '../../data/repository.dart';
import '../../data/sync_queue.dart';
import '../../widgets/async_view.dart';
import '../../widgets/confirm_dialog.dart';
import '../../widgets/league_picker.dart';
import '../match/match_screen.dart';

/// Organizer only: append score events and compensating events. Queued when offline.
class ScoringScreen extends ConsumerStatefulWidget {
  final String? initialMatchId;
  const ScoringScreen({super.key, this.initialMatchId});

  @override
  ConsumerState<ScoringScreen> createState() => _ScoringScreenState();
}

class _ScoringScreenState extends ConsumerState<ScoringScreen> {
  late String? _matchId = widget.initialMatchId;
  bool _homeSelected = true;
  bool _busy = false;

  @override
  Widget build(BuildContext context) {
    final session = ref.watch(sessionProvider);
    if (session == null || !session.canScore) {
      return Scaffold(
        appBar: AppBar(title: const Text('Scoring')),
        body: const EmptyState(message: 'Only league organizers can enter scores.', icon: Icons.lock_outline),
      );
    }
    return Scaffold(
      appBar: AppBar(title: const Text('Scoring entry')),
      body: LeagueScoped(builder: (context, league) {
        final fixtures = ref.watch(fixturesProvider(league.leagueId));
        return AsyncView<List<Fixture>>(
          value: fixtures,
          onRetry: () => ref.invalidate(fixturesProvider(league.leagueId)),
          isEmpty: (l) => l.where((f) => f.status != 'completed').isEmpty,
          emptyMessage: 'No live or upcoming matches to score',
          builder: (list) {
            final open = list.where((f) => f.status != 'completed').toList();
            return ListView(padding: const EdgeInsets.all(16), children: [
              Text('Match', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              Wrap(spacing: 8, runSpacing: 8, children: [
                for (final f in open)
                  ChoiceChip(
                    label: Text('${f.homeName} vs ${f.awayName}'),
                    selected: _matchId == f.matchId,
                    onSelected: (_) => setState(() => _matchId = f.matchId),
                  ),
              ]),
              if (_matchId == null)
                const Padding(padding: EdgeInsets.only(top: 24), child: Text('Choose a match to start scoring.'))
              else
                _MatchScoring(
                  matchId: _matchId!,
                  homeSelected: _homeSelected,
                  busy: _busy,
                  onTeamChanged: (home) => setState(() => _homeSelected = home),
                  onSubmit: _submit,
                ),
            ]);
          },
        );
      }),
    );
  }

  /// Sends one §7.6 event. Offline: queues it as a §7.11 score_event with the last seen version.
  Future<void> _submit(MatchDetail match, String type, Map<String, dynamic> payload, String successText) async {
    final body = {'event_id': 'evt-${const Uuid().v4()}', 'match_id': match.matchId, 'type': type, 'payload': payload};
    if (ref.read(syncProvider).isOffline) {
      await ref.read(syncProvider.notifier).enqueue(type: 'score_event', baseVersion: match.version, payload: body);
      if (mounted) showSuccess(context, "Saved as pending. It will sync when you're back online.");
      return;
    }
    setState(() => _busy = true);
    try {
      await ref.read(repositoryProvider).postEvent(body);
      ref.invalidate(matchProvider(match.matchId));
      if (mounted) showSuccess(context, successText);
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }
}

class _MatchScoring extends ConsumerWidget {
  final String matchId;
  final bool homeSelected;
  final bool busy;
  final ValueChanged<bool> onTeamChanged;
  final Future<void> Function(MatchDetail, String, Map<String, dynamic>, String) onSubmit;

  const _MatchScoring({
    required this.matchId,
    required this.homeSelected,
    required this.busy,
    required this.onTeamChanged,
    required this.onSubmit,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final match = ref.watch(matchProvider(matchId));
    return match.when(
      loading: () => const Padding(padding: EdgeInsets.all(24), child: LoadingView()),
      error: (e, _) => ErrorView(message: 'Could not load this match.', onRetry: () => ref.invalidate(matchProvider(matchId))),
      data: (m) {
        final eventTypes = ref.watch(eventTypesProvider(m.sportId));
        final team = homeSelected ? m.home : m.away;
        return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          ScoreBoard(match: m),
          if (m.status == 'upcoming')
            FilledButton.icon(
              onPressed: busy ? null : () => onSubmit(m, 'match_start', {}, 'Match started.'),
              icon: const Icon(Icons.play_arrow),
              label: const Text('Start match'),
            ),
          if (m.status == 'in_progress') ...[
            Text('Team', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            SegmentedButton<bool>(
              segments: [
                ButtonSegment(value: true, label: Text(m.home.name, overflow: TextOverflow.ellipsis)),
                ButtonSegment(value: false, label: Text(m.away.name, overflow: TextOverflow.ellipsis)),
              ],
              selected: {homeSelected},
              onSelectionChanged: (s) => onTeamChanged(s.first),
            ),
            const SizedBox(height: 16),
            Text('Add event for ${team.name}', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            eventTypes.when(
              loading: () => const LinearProgressIndicator(),
              error: (e, _) => const Text("Couldn't load this sport's event types."),
              data: (types) => Wrap(spacing: 8, runSpacing: 8, children: [
                for (final t in types)
                  FilledButton.tonal(
                    onPressed: busy
                        ? null
                        : () => onSubmit(m, 'score', {'team_id': team.teamId, 'event_type': t}, '${humanize(t)} added for ${team.name}.'),
                    child: Text(humanize(t)),
                  ),
              ]),
            ),
            const SizedBox(height: 16),
            OutlinedButton.icon(
              onPressed: busy
                  ? null
                  : () async {
                      final ok = await confirmAction(context, title: 'End match?', message: 'The final score will be locked in.', confirmLabel: 'End match');
                      if (ok) await onSubmit(m, 'match_end', {}, 'Match ended.');
                    },
              icon: const Icon(Icons.stop),
              label: const Text('End match'),
            ),
          ],
          const SectionHeader('Events'),
          if (m.events.isEmpty) const Text('No events yet.'),
          for (final e in m.events.reversed)
            EventTile(
              event: e,
              match: m,
              trailing: e.canBeCompensated
                  ? TextButton(onPressed: busy ? null : () => _compensate(context, m, e), child: const Text('Correct'))
                  : null,
            ),
        ]);
      },
    );
  }

  Future<void> _compensate(BuildContext context, MatchDetail m, MatchEvent e) async {
    final reason = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Correct this event?'),
        content: Column(mainAxisSize: MainAxisSize.min, children: [
          Text('Event #${e.sequence} will be cancelled out by a correction. The original stays in the log.'),
          const SizedBox(height: 12),
          TextField(controller: reason, decoration: const InputDecoration(labelText: 'Reason')),
        ]),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Correct')),
        ],
      ),
    );
    final text = reason.text.trim();
    reason.dispose();
    if (ok != true) return;
    await onSubmit(m, 'compensation', {'compensates': e.eventId, 'reason': text.isEmpty ? 'Correction' : text}, 'Correction added.');
  }
}
