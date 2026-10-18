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
import '../../widgets/league_picker.dart';
import '../../widgets/player_card.dart';
import '../../widgets/team_crest.dart';
import '../../widgets/ui.dart';
import '../fixtures/fixtures_screen.dart';

/// Organizer only: append score events and corrections (compensating events). Queued when offline.
class ScoringScreen extends ConsumerStatefulWidget {
  final String? initialMatchId;
  const ScoringScreen({super.key, this.initialMatchId});

  @override
  ConsumerState<ScoringScreen> createState() => _ScoringScreenState();
}

class _ScoringScreenState extends ConsumerState<ScoringScreen> {
  late String? _matchId = widget.initialMatchId;
  bool _homeSelected = true;
  String? _eventType;
  String? _playerId;
  int _minute = 1;
  bool _busy = false;

  static const _scorable = {'upcoming', 'in_progress', 'postponed'};

  @override
  Widget build(BuildContext context) {
    final session = ref.watch(sessionProvider);
    final p = context.palette;
    final tag = Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Tag('Organizer', color: p.accent, outlined: true, fontSize: 12),
    );
    if (session == null || !session.canScore) {
      return const FlatPage(
        title: 'Score entry',
        children: [EmptyState(message: 'Only league organizers can enter scores.', icon: Icons.lock_outline_rounded)],
      );
    }
    if (_matchId == null) {
      return FlatPage(
        title: 'Score entry',
        backLabel: 'Me',
        backFallback: '/more',
        titleTrailing: tag,
        children: [const SectionLabel('Choose a match'), _MatchChooser(scorable: _scorable, onPick: (id) => setState(() => _matchId = id))],
      );
    }

    final match = ref.watch(matchProvider(_matchId!));
    final m = match.value;
    final team = m == null ? null : (_homeSelected ? m.home : m.away);
    final types = m == null ? null : ref.watch(eventTypesProvider(m.sportId)).value;
    final typeLabel = types?.where((t) => t.key == _eventType).firstOrNull?.label;
    final canRecord = m != null && m.status == 'in_progress' && _eventType != null && !_busy;

    return FlatPage(
      title: 'Score entry',
      backLabel: widget.initialMatchId == null ? 'Matches' : 'Match',
      backFallback: '/fixtures',
      titleTrailing: tag,
      onRefresh: () => ref.refresh(matchProvider(_matchId!).future),
      actions: m == null || m.status != 'in_progress'
          ? null
          : [
              PrimaryButton(
                label: _eventType == null
                    ? 'Choose an event'
                    : 'Record ${(typeLabel ?? humanize(_eventType!)).toLowerCase()} · ${initialsOf(team!.name)} $_minute′',
                loading: _busy,
                onPressed: canRecord
                    ? () => _submit(
                          m,
                          'score',
                          {
                            'team_id': team!.teamId,
                            'event_type': _eventType,
                            'minute': _minute,
                            'player_id': ?_playerId,
                          },
                          '${typeLabel ?? humanize(_eventType!)} recorded for ${team.name}.',
                        )
                    : null,
              ),
            ],
      children: [
        AsyncView<MatchDetail>(
          value: match,
          onRetry: () => ref.invalidate(matchProvider(_matchId!)),
          builder: (m) => _MatchScoring(
            match: m,
            busy: _busy,
            homeSelected: _homeSelected,
            eventType: _eventType,
            playerId: _playerId,
            minute: _minute,
            canChangeMatch: widget.initialMatchId == null,
            onChangeMatch: () => setState(() {
              _matchId = null;
              _eventType = null;
              _playerId = null;
            }),
            onTeam: (home) => setState(() {
              _homeSelected = home;
              _playerId = null;
            }),
            onType: (t) => setState(() => _eventType = t),
            onPlayer: (id) => setState(() => _playerId = id),
            onMinute: (v) => setState(() => _minute = v),
            onSubmit: _submit,
            onStatus: _changeStatus,
          ),
        ),
      ],
    );
  }

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

/// Live and upcoming matches in the current league, as fixture cards that select instead of navigate.
class _MatchChooser extends ConsumerWidget {
  final Set<String> scorable;
  final ValueChanged<String> onPick;
  const _MatchChooser({required this.scorable, required this.onPick});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final league = watchCurrentLeague(ref);
    if (league == null) return const LoadingView();
    final fixtures = ref.watch(fixturesProvider(league.leagueId));
    return AsyncView<List<Fixture>>(
      value: fixtures,
      onRetry: () => ref.invalidate(fixturesProvider(league.leagueId)),
      isEmpty: (l) => !l.any((f) => scorable.contains(f.status)),
      emptyMessage: 'No live or upcoming matches to score',
      builder: (all) => Column(children: [
        for (final f in all.where((f) => scorable.contains(f.status))) ...[
          GestureDetector(
            onTap: () => onPick(f.matchId),
            child: AbsorbPointer(child: f.status == 'in_progress' ? LiveFixtureCard(fixture: f) : FixtureCard(fixture: f)),
          ),
          const SizedBox(height: 12),
        ],
      ]),
    );
  }
}

class _MatchScoring extends ConsumerWidget {
  final MatchDetail match;
  final bool busy;
  final bool homeSelected;
  final String? eventType;
  final String? playerId;
  final int minute;
  final bool canChangeMatch;
  final VoidCallback onChangeMatch;
  final ValueChanged<bool> onTeam;
  final ValueChanged<String> onType;
  final ValueChanged<String?> onPlayer;
  final ValueChanged<int> onMinute;
  final Future<void> Function(MatchDetail, String, Map<String, dynamic>, String) onSubmit;
  final Future<void> Function(MatchDetail, String to) onStatus;

  const _MatchScoring({
    required this.match,
    required this.busy,
    required this.homeSelected,
    required this.eventType,
    required this.playerId,
    required this.minute,
    required this.canChangeMatch,
    required this.onChangeMatch,
    required this.onTeam,
    required this.onType,
    required this.onPlayer,
    required this.onMinute,
    required this.onSubmit,
    required this.onStatus,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final m = match;
    final p = context.palette;
    final team = homeSelected ? m.home : m.away;
    final eventTypes = ref.watch(eventTypesProvider(m.sportId));
    final roster = ref.watch(clubProvider(team.teamId)).value?.roster ?? const <RosterPlayer>[];
    final player = roster.where((r) => r.playerId == playerId).firstOrNull;
    final last = m.events.reversed.where((e) => e.canBeCompensated).firstOrNull;
    final names = {
      for (final id in [m.home.teamId, m.away.teamId])
        for (final r in ref.watch(clubProvider(id)).value?.roster ?? const <RosterPlayer>[]) r.playerId: r.name,
    };

    Widget teamButton(TeamScore s, bool home) {
      final on = home == homeSelected;
      return Expanded(
        child: Semantics(
          button: true,
          selected: on,
          label: s.name,
          excludeSemantics: true,
          child: GestureDetector(
            onTap: () => onTeam(home),
            child: Container(
              height: 52,
              padding: const EdgeInsets.symmetric(horizontal: 10),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: on ? p.accent : p.border, width: on ? 2 : 1),
              ),
              child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                TeamCrest(teamId: s.teamId, name: s.name, size: 22),
                const SizedBox(width: 8),
                Flexible(
                  child: Text(
                    s.name.toUpperCase(),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: condensed(16, weight: FontWeight.w700, color: on ? p.label : p.label2),
                  ),
                ),
              ]),
            ),
          ),
        ),
      );
    }

    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      // Scoreline summary.
      Panel(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        borderColor: m.status == 'in_progress' ? null : p.border,
        child: Row(children: [
          TeamCrest(teamId: m.home.teamId, name: m.home.name, size: 26),
          const SizedBox(width: 8),
          Text('${initialsOf(m.home.name)} ${m.home.display}–${m.away.display} ${initialsOf(m.away.name)}',
              style: condensed(26, weight: FontWeight.w800, color: p.label)),
          const SizedBox(width: 8),
          TeamCrest(teamId: m.away.teamId, name: m.away.name, size: 26),
          const Spacer(),
          MatchStatusLabel(status: m.status, scheduledAt: m.scheduledAt),
        ]),
      ),
      if (canChangeMatch)
        Align(alignment: Alignment.centerRight, child: TextButton(onPressed: onChangeMatch, child: const Text('CHANGE MATCH'))),
      const SizedBox(height: 8),

      if (m.status == 'upcoming') ...[
        PrimaryButton(
          label: 'Start match',
          icon: Icons.play_arrow_rounded,
          onPressed: busy ? null : () => onSubmit(m, 'match_start', {}, 'Match started.'),
        ),
        const SizedBox(height: 20),
      ],

      if (m.status == 'in_progress') ...[
        Row(children: [teamButton(m.home, true), const SizedBox(width: 8), teamButton(m.away, false)]),
        const SizedBox(height: 14),
        eventTypes.when(
          loading: () => const Padding(padding: EdgeInsets.all(16), child: LoadingView()),
          error: (_, _) => Text('Couldn’t load this sport’s events.', style: TextStyle(color: p.label3)),
          data: (types) => GridView.count(
            crossAxisCount: 3,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            mainAxisSpacing: 8,
            crossAxisSpacing: 8,
            childAspectRatio: 1.8,
            children: [
              for (final t in types)
                Semantics(
                  button: true,
                  selected: t.key == eventType,
                  label: t.label,
                  excludeSemantics: true,
                  child: Material(
                    color: t.key == eventType ? p.accent : p.surface,
                    borderRadius: BorderRadius.circular(12),
                    child: InkWell(
                      borderRadius: BorderRadius.circular(12),
                      onTap: () => onType(t.key),
                      child: Center(
                        child: Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 6),
                          child: Text(
                            t.label.toUpperCase(),
                            textAlign: TextAlign.center,
                            maxLines: 2,
                            style: condensed(15, weight: FontWeight.w700, tracking: 0.5, color: t.key == eventType ? p.onAccent : p.label),
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ),
        const SizedBox(height: 10),
        Row(children: [
          Expanded(
            child: PickerField(
              text: player?.name ?? 'Player (optional)',
              detail: player?.position,
              placeholder: player == null,
              onTap: roster.isEmpty
                  ? null
                  : () async {
                      final id = await showChoiceSheet<String>(
                        context,
                        title: 'Who?',
                        selected: playerId ?? '',
                        leading: (id) => id.isEmpty
                            ? const SizedBox(width: 32)
                            : PlayerAvatar(playerId: id, name: roster.firstWhere((r) => r.playerId == id).name, clubId: team.teamId, size: 32),
                        options: [('', 'No player'), for (final r in roster) (r.playerId, '${r.name} · ${r.position}')],
                      );
                      if (id != null) onPlayer(id.isEmpty ? null : id);
                    },
            ),
          ),
          const SizedBox(width: 8),
          QuantityStepper(value: minute, min: 1, max: 130, format: (v) => '$v′', onChanged: onMinute),
        ]),
        if (last != null) ...[
          const SizedBox(height: 12),
          Container(
            padding: const EdgeInsets.symmetric(vertical: 12),
            decoration: BoxDecoration(border: Border(top: BorderSide(color: p.raised))),
            child: Row(children: [
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('Last recorded', style: TextStyle(fontSize: 14, color: p.label3)),
                  Text(_describe(m, last, names), style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700, color: p.label)),
                ]),
              ),
              _CorrectButton(onPressed: busy ? null : () => _compensate(context, m, last, names)),
            ]),
          ),
        ],
        // Level score in a sport without draws: the shootout / super-over winner settles it.
        if (m.home.score == m.away.score) ...[
          const SizedBox(height: 8),
          SecondaryButton(
            label: '${team.name} won the tiebreak',
            icon: Icons.emoji_events_outlined,
            onPressed: busy ? null : () => onSubmit(m, 'tiebreak_winner', {'team_id': team.teamId}, 'Tiebreak winner: ${team.name}.'),
          ),
        ],
        const SizedBox(height: 10),
        SecondaryButton(
          label: 'End match',
          icon: Icons.flag_outlined,
          destructive: true,
          onPressed: busy
              ? null
              : () async {
                  final ok = await confirmAction(context,
                      title: 'End match?', message: 'The final score will be locked in.', confirmLabel: 'End match', destructive: true);
                  if (ok) await onSubmit(m, 'match_end', {}, 'Match ended.');
                },
        ),
      ],

      if (m.statusTargets.isNotEmpty) ...[
        const SectionLabel('Match status', padding: EdgeInsets.only(top: 22, bottom: 8)),
        Wrap(spacing: 8, runSpacing: 8, children: [
          for (final to in m.statusTargets)
            SizedBox(
              width: 150,
              child: SecondaryButton(
                label: _statusVerbs[to] ?? humanize(to),
                height: 48,
                destructive: to == 'cancelled' || to == 'abandoned',
                onPressed: busy ? null : () => onStatus(m, to),
              ),
            ),
        ]),
        Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Text('Needs a connection. Postponed matches can be put back on the schedule later.',
              style: TextStyle(fontSize: 13, color: p.label3, height: 1.4)),
        ),
      ],

      const SectionLabel('All events', padding: EdgeInsets.only(top: 22, bottom: 4)),
      if (m.events.where((e) => e.type != 'match_init' && e.type != 'compensation').isEmpty)
        Text('No events yet.', style: TextStyle(color: p.label3))
      else
        for (final e in m.events.reversed.where((e) => e.type != 'match_init' && e.type != 'compensation'))
          Container(
            padding: const EdgeInsets.symmetric(vertical: 8),
            decoration: BoxDecoration(border: Border(bottom: BorderSide(color: p.hairline))),
            child: Row(children: [
              Expanded(
                child: Text(
                  _describe(m, e, names),
                  style: TextStyle(
                    fontSize: 14,
                    color: e.compensated ? p.label3 : p.label,
                    decoration: e.compensated ? TextDecoration.lineThrough : null,
                    decorationColor: p.label3,
                  ),
                ),
              ),
              if (e.canBeCompensated) _CorrectButton(onPressed: busy ? null : () => _compensate(context, m, e, names)),
            ]),
          ),
      Padding(
        padding: const EdgeInsets.only(top: 10),
        child: Text('Correct adds a new event that cancels the old one. The original stays in the log.',
            style: TextStyle(fontSize: 13, color: p.label3, height: 1.4)),
      ),
    ]);
  }

  /// "64′ Goal · Hamza R. · KK"
  static String _describe(MatchDetail m, MatchEvent e, Map<String, String> names) {
    final teamId = e.payload['team_id'] as String?;
    final player = names[e.payload['player_id']];
    final what = switch (e.type) {
      'score' => humanize('${e.payload['event_type'] ?? 'score'}'),
      'discipline' => 'Discipline (${e.payload['points']})',
      'tiebreak_winner' => 'Tiebreak won',
      'match_start' => 'Kick-off',
      'match_end' => 'Full time',
      _ => humanize(e.type),
    };
    return [
      '${e.payload['minute'] is num ? '${e.payload['minute']}′' : '#${e.sequence}'} $what',
      if (player != null) shortName(player),
      if (teamId != null) initialsOf(m.teamName(teamId)),
    ].join(' · ');
  }

  Future<void> _compensate(BuildContext context, MatchDetail m, MatchEvent e, Map<String, String> names) async {
    final reason = TextEditingController();
    final ok = await confirmAction(
      context,
      title: 'Correct this event?',
      message: '${_describe(m, e, names)}\nA correction cancels it out. The original stays in the log.',
      confirmLabel: 'Correct',
      destructive: true,
      extra: TextField(controller: reason, autofocus: true, decoration: const InputDecoration(hintText: 'Reason, e.g. offside')),
    );
    final text = reason.text.trim();
    reason.dispose();
    if (!ok) return;
    await onSubmit(m, 'compensation', {'compensates': e.eventId, 'reason': text.isEmpty ? 'Correction' : text}, 'Correction added.');
  }
}

class _CorrectButton extends StatelessWidget {
  final VoidCallback? onPressed;
  const _CorrectButton({this.onPressed});

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    final c = onPressed == null ? p.muted : p.warning;
    return Semantics(
      button: true,
      enabled: onPressed != null,
      label: 'Correct this event',
      excludeSemantics: true,
      child: Material(
        color: Colors.transparent,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10), side: BorderSide(color: c)),
        child: InkWell(
          borderRadius: BorderRadius.circular(10),
          onTap: onPressed,
          child: SizedBox(
            height: 44,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 14),
              child: Center(child: Text('↺ CORRECT', style: condensed(14, weight: FontWeight.w700, tracking: 1, color: c))),
            ),
          ),
        ),
      ),
    );
  }
}

const _statusVerbs = {'postponed': 'Postpone', 'abandoned': 'Abandon', 'cancelled': 'Cancel', 'upcoming': 'Reschedule'};
const _statusDone = {'postponed': 'postponed', 'abandoned': 'abandoned', 'cancelled': 'cancelled', 'upcoming': 'rescheduled'};
