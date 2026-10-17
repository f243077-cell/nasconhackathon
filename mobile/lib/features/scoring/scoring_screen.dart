import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:uuid/uuid.dart';

import '../../core/format.dart';
import '../../core/session.dart';
import '../../core/theme.dart';
import '../../data/models.dart';
import '../../data/repository.dart';
import '../../data/sync_queue.dart';
import '../../widgets/async_view.dart';
import '../../widgets/confirm_dialog.dart';
import '../../widgets/team_crest.dart';
import '../../widgets/ui.dart';
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
        body: const EmptyState(message: 'Only league organizers can enter scores.', icon: Icons.lock_rounded),
      );
    }
    final leagues = ref.watch(leaguesProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Scoring')),
      body: AsyncView<List<League>>(
        value: leagues,
        onRetry: () => ref.invalidate(leaguesProvider),
        isEmpty: (l) => l.isEmpty,
        emptyMessage: 'No leagues yet',
        builder: (list) {
          final selected = ref.watch(selectedLeagueProvider);
          final league = list.firstWhere((l) => l.leagueId == selected, orElse: () => list.first);
          final fixtures = ref.watch(fixturesProvider(league.leagueId));
          return AsyncView<List<Fixture>>(
            value: fixtures,
            onRetry: () => ref.invalidate(fixturesProvider(league.leagueId)),
            isEmpty: (l) => !l.any((f) => _scorable.contains(f.status)),
            emptyMessage: 'No live or upcoming matches to score',
            builder: (all) {
              final open = all.where((f) => _scorable.contains(f.status)).toList();
              return ListView(padding: const EdgeInsets.only(top: 12, bottom: 32), children: [
                Section(header: 'Match', children: [
                  for (final f in open)
                    ListTile(
                      title: Text('${f.homeName} vs ${f.awayName}', overflow: TextOverflow.ellipsis),
                      subtitle: Text(formatDateTime(f.scheduledAt)),
                      trailing: Row(mainAxisSize: MainAxisSize.min, children: [
                        MatchStatusLabel(status: f.status, scheduledAt: f.scheduledAt),
                        SizedBox(
                          width: 32,
                          child: _matchId == f.matchId
                              ? Icon(Icons.check_rounded, color: context.palette.accent, semanticLabel: 'Selected')
                              : null,
                        ),
                      ]),
                      onTap: () => setState(() => _matchId = f.matchId),
                    ),
                ]),
                if (_matchId == null)
                  const EmptyState(message: 'Choose a match to start scoring.', icon: Icons.scoreboard_rounded)
                else
                  _MatchScoring(
                    matchId: _matchId!,
                    homeSelected: _homeSelected,
                    busy: _busy,
                    onTeamChanged: (home) => setState(() => _homeSelected = home),
                    onSubmit: _submit,
                    onStatus: _changeStatus,
                  ),
              ]);
            },
          );
        },
      ),
    );
  }

  static const _scorable = {'upcoming', 'in_progress', 'postponed'};

  /// FR-1.3 status change (postpone / abandon / cancel / back to upcoming). Online only:
  /// the offline queue carries score events and roster moves, not schedule changes.
  Future<void> _changeStatus(MatchDetail match, String to) async {
    final verb = _statusVerbs[to] ?? humanize(to);
    final ok = await confirmAction(
      context,
      title: '$verb this match?',
      message: switch (to) {
        'upcoming' => 'The match goes back on the schedule as upcoming.',
        'postponed' => 'Fans will see the match as postponed until it is rescheduled.',
        _ => 'This can’t be undone. The match won’t count in the standings.',
      },
      confirmLabel: verb,
      destructive: to == 'cancelled' || to == 'abandoned',
    );
    if (!ok || !mounted) return;
    setState(() => _busy = true);
    try {
      await ref.read(repositoryProvider).setMatchStatus(match.matchId, to);
      ref.invalidate(matchProvider(match.matchId));
      ref.invalidate(fixturesProvider);
      if (mounted) showSuccess(context, 'Match ${_statusDone[to] ?? humanize(to).toLowerCase()}.');
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  /// Sends one §7.6 event. Offline: queues it as a §7.11 score_event with the last seen version.
  Future<void> _submit(MatchDetail match, String type, Map<String, dynamic> payload, String successText) async {
    final body = {'event_id': 'evt-${const Uuid().v4()}', 'match_id': match.matchId, 'type': type, 'payload': payload};
    if (ref.read(syncProvider).isOffline) {
      await ref.read(syncProvider.notifier).enqueue(type: 'score_event', baseVersion: match.version, payload: body);
      if (mounted) showSuccess(context, 'Saved. It will sync when you’re back online.');
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
  final Future<void> Function(MatchDetail, String to) onStatus;

  const _MatchScoring({
    required this.matchId,
    required this.homeSelected,
    required this.busy,
    required this.onTeamChanged,
    required this.onSubmit,
    required this.onStatus,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final match = ref.watch(matchProvider(matchId));
    final t = Theme.of(context).textTheme;
    return match.when(
      loading: () => const Padding(padding: EdgeInsets.all(32), child: LoadingView()),
      error: (e, _) => ErrorView(message: 'Couldn’t load this match.', onRetry: () => ref.invalidate(matchProvider(matchId))),
      data: (m) {
        final eventTypes = ref.watch(eventTypesProvider(m.sportId));
        final team = homeSelected ? m.home : m.away;
        return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          ScoreBoard(match: m, compact: true),
          if (m.status == 'upcoming')
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 28),
              child: PrimaryButton(
                label: 'Start Match',
                icon: Icons.play_arrow_rounded,
                onPressed: busy ? null : () => onSubmit(m, 'match_start', {}, 'Match started.'),
              ),
            ),
          if (m.status == 'in_progress') ...[
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 20),
              child: Segmented<bool>(
                value: homeSelected,
                options: {true: m.home.name, false: m.away.name},
                onChanged: onTeamChanged,
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(32, 0, 32, 10),
              child: Text('Add for ${team.name}', style: t.bodySmall!.copyWith(fontWeight: FontWeight.w600)),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
              child: eventTypes.when(
                loading: () => const Center(child: CupertinoActivityIndicator()),
                error: (e, _) => const Text('Couldn’t load this sport’s events.'),
                data: (types) => Wrap(spacing: 10, runSpacing: 10, children: [
                  for (final type in types)
                    OutlinedButton(
                      onPressed: busy
                          ? null
                          : () => onSubmit(m, 'score', {'team_id': team.teamId, 'event_type': type.key},
                              '${type.label} added for ${team.name}.'),
                      child: Text(type.label),
                    ),
                ]),
              ),
            ),
            // Level score in a sport without draws: the shootout / super-over winner settles it.
            if (m.home.score == m.away.score)
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                child: SecondaryButton(
                  label: '${team.name} Won the Tiebreak',
                  icon: Icons.emoji_events_rounded,
                  onPressed: busy
                      ? null
                      : () => onSubmit(m, 'tiebreak_winner', {'team_id': team.teamId}, 'Tiebreak winner: ${team.name}.'),
                ),
              ),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 28),
              child: SecondaryButton(
                label: 'End Match',
                icon: Icons.flag_rounded,
                destructive: true,
                onPressed: busy
                    ? null
                    : () async {
                        final ok = await confirmAction(context,
                            title: 'End Match?', message: 'The final score will be locked in.', confirmLabel: 'End Match', destructive: true);
                        if (ok) await onSubmit(m, 'match_end', {}, 'Match ended.');
                      },
              ),
            ),
          ],
          if (m.statusTargets.isNotEmpty)
            Section(
              header: 'Match Status',
              footer: 'Needs a connection. Postponed matches can be put back on the schedule later.',
              children: [
                for (final to in m.statusTargets)
                  ListTile(
                    title: Text(_statusVerbs[to] ?? humanize(to),
                        style: TextStyle(
                            color: to == 'cancelled' || to == 'abandoned' ? context.palette.danger : context.palette.accent)),
                    enabled: !busy,
                    onTap: () => onStatus(m, to),
                  ),
              ],
            ),
          Section(
            header: 'Events',
            footer: 'Correct adds a new event that cancels the old one. The original stays in the log.',
            dividerIndent: 60,
            children: m.events.isEmpty
                ? [const ListTile(title: Text('No events yet'))]
                : [
                    for (final e in m.events.reversed)
                      EventTile(
                        event: e,
                        match: m,
                        trailing: e.canBeCompensated
                            ? TextButton(onPressed: busy ? null : () => _compensate(context, m, e), child: const Text('Correct'))
                            : null,
                      ),
                  ],
          ),
        ]);
      },
    );
  }

  Future<void> _compensate(BuildContext context, MatchDetail m, MatchEvent e) async {
    final reason = TextEditingController();
    final ok = await showCupertinoDialog<bool>(
      context: context,
      barrierDismissible: true,
      builder: (ctx) => CupertinoAlertDialog(
        title: Text('Correct Event ${e.sequence}?'),
        content: Column(mainAxisSize: MainAxisSize.min, children: [
          const SizedBox(height: 6),
          const Text('A correction cancels it out. The original stays in the log.'),
          const SizedBox(height: 12),
          CupertinoTextField(controller: reason, placeholder: 'Reason', autofocus: true),
        ]),
        actions: [
          CupertinoDialogAction(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          CupertinoDialogAction(isDestructiveAction: true, onPressed: () => Navigator.pop(ctx, true), child: const Text('Correct')),
        ],
      ),
    );
    final text = reason.text.trim();
    reason.dispose();
    if (ok != true) return;
    await onSubmit(m, 'compensation', {'compensates': e.eventId, 'reason': text.isEmpty ? 'Correction' : text}, 'Correction added.');
  }
}

const _statusVerbs = {'postponed': 'Postpone', 'abandoned': 'Abandon', 'cancelled': 'Cancel', 'upcoming': 'Reschedule'};
const _statusDone = {'postponed': 'postponed', 'abandoned': 'abandoned', 'cancelled': 'cancelled', 'upcoming': 'rescheduled'};
