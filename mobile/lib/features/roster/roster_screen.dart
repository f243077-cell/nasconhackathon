import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:uuid/uuid.dart';

import '../../core/errors.dart';
import '../../core/format.dart';
import '../../data/models.dart';
import '../../core/theme.dart';
import '../../data/repository.dart';
import '../../data/sync_queue.dart';
import '../../widgets/async_view.dart';
import '../../widgets/confirm_dialog.dart';
import '../../widgets/player_card.dart';
import '../../widgets/team_crest.dart';
import '../../widgets/ui.dart';

/// Club Manager only: transfer, loan or release a player from [club]. Opens the Roster action
/// sheet, confirms, then sends it (or queues it when offline).
Future<void> openRosterAction(BuildContext context, WidgetRef ref, Session session, Club club, {RosterPlayer? player}) async {
  final body = await showModalBottomSheet<Map<String, dynamic>>(
    context: context,
    isScrollControlled: true,
    useSafeArea: true,
    builder: (_) => RosterActionSheet(club: club, initialPlayer: player, session: session),
  );
  if (body == null || !context.mounted) return;

  final target = club.roster.firstWhere((p) => p.playerId == body['player_id']);
  final type = body['type'] as String;
  final verb = humanize(type);
  final ok = await confirmAction(
    context,
    title: '$verb ${target.name}?',
    message: type == 'release'
        ? '${target.name} will leave the squad. This can’t be undone here.'
        : '${target.name} moves on ${body['effective_date']}.',
    confirmLabel: verb,
    destructive: type == 'release',
  );
  if (!ok || !context.mounted) return;

  final leagueId = body['league_id'] as String;
  final sync = ref.read(syncProvider.notifier);
  if (ref.read(syncProvider).isOffline) {
    // §7.11: base_version = the player's audit entry count (from the cached history).
    var baseVersion = 0;
    try {
      baseVersion = (await ref.read(repositoryProvider).rosterHistory(target.playerId)).entries.length;
    } catch (_) {
      // never opened online: 0 is never ahead of the server, so it rebases instead of failing
    }
    await sync.enqueue(type: 'roster_transfer', baseVersion: baseVersion, payload: body);
    if (context.mounted) showSuccess(context, 'Saved. It will sync when you’re back online.');
    return;
  }
  try {
    final res = await ref.read(repositoryProvider).rosterTransfer(body);
    ref.invalidate(clubProvider(club.clubId));
    ref.invalidate(squadsProvider(leagueId));
    ref.invalidate(rosterHistoryProvider(target.playerId));
    if (res['state'] == 'deferred_until_match_end') {
      if (context.mounted) showSuccess(context, '${target.name}: $verb accepted. It takes effect after the current match.');
      return;
    }
    if (context.mounted) showSuccess(context, '${target.name}: $verb complete.');
  } catch (e) {
    if (context.mounted) showError(context, e);
  }
}

/// Bottom-sheet form. Pops with the exact §7.8 transfer body, or null on cancel.
class RosterActionSheet extends ConsumerStatefulWidget {
  final Club club;
  final RosterPlayer? initialPlayer;
  final Session session;
  const RosterActionSheet({super.key, required this.club, required this.session, this.initialPlayer});

  @override
  ConsumerState<RosterActionSheet> createState() => _RosterActionSheetState();
}

class _RosterActionSheetState extends ConsumerState<RosterActionSheet> {
  final _reason = TextEditingController();
  String _type = 'transfer'; // transfer | loan | release
  late RosterPlayer? _player = widget.initialPlayer;
  String? _toSquad;
  DateTime _effective = DateTime.now();
  DateTime? _loanEnd;
  String? _error;

  @override
  void initState() {
    super.initState();
    _warmHistory();
  }

  @override
  void dispose() {
    _reason.dispose();
    super.dispose();
  }

  // Warm the history cache while the form is open: its length is the offline base_version.
  void _warmHistory() {
    if (_player != null) ref.read(rosterHistoryProvider(_player!.playerId).future).ignore();
  }

  String get _leagueId =>
      _player?.leagueId ?? widget.session.user.leagueId ?? ref.read(selectedLeagueProvider) ?? '';

  Future<void> _choosePlayer() async {
    final chosen = await showChoiceSheet<RosterPlayer>(
      context,
      title: 'Choose a player',
      selected: _player,
      leading: (pl) => PlayerAvatar(playerId: pl.playerId, name: pl.name, clubId: widget.club.clubId, size: 32),
      options: [for (final pl in widget.club.roster) (pl, '${pl.name} · ${pl.position}${pl.onLoan ? ' · on loan' : ''}')],
    );
    if (chosen == null) return;
    setState(() {
      _player = chosen;
      _toSquad = null;
      _error = null;
    });
    _warmHistory();
  }

  Future<void> _chooseSquad(List<Map<String, dynamic>> squads) async {
    final id = await showChoiceSheet<String>(
      context,
      title: 'To club',
      selected: _toSquad,
      leading: (id) {
        final s = squads.firstWhere((s) => s['squad_id'] == id);
        return TeamCrest(teamId: '${s['club_id'] ?? id}', name: '${s['name']}', size: 26);
      },
      options: [for (final s in squads.where((s) => s['squad_id'] != _player?.squadId)) (s['squad_id'] as String, '${s['name']}')],
    );
    if (id != null) setState(() => _toSquad = id);
  }

  void _submit() {
    final isRelease = _type == 'release';
    final isLoan = _type == 'loan';
    String? error;
    if (_reason.text.trim().isEmpty) error = 'Add a short reason.';
    if (isLoan && (_loanEnd == null || !_loanEnd!.isAfter(_effective))) error = 'The loan must end after it starts.';
    if (!isRelease && _toSquad == null) error = 'Choose where the player is going.';
    if (_player == null) error = 'Choose a player.';
    if (error != null) {
      setState(() => _error = error);
      return;
    }
    Navigator.pop(context, {
      'request_id': 'tr-${const Uuid().v4()}',
      'league_id': _leagueId,
      'player_id': _player!.playerId,
      'type': _type,
      'from_squad_id': _player!.squadId,
      'to_squad_id': isRelease ? null : _toSquad,
      'effective_date': formatApiDate(_effective),
      if (isLoan) 'loan_end_date': formatApiDate(_loanEnd!),
      'reason': _reason.text.trim(),
      'requested_by': widget.session.user.id,
    });
  }

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    final isRelease = _type == 'release';
    final squads = _player == null || isRelease ? null : ref.watch(squadsProvider(_leagueId));
    final offline = ref.watch(syncProvider).isOffline;

    Widget dateField(String label, DateTime? value, ValueChanged<DateTime> onPicked, DateTime fallback) => Expanded(
          child: LabeledField(
            label: label,
            child: PickerField(
              text: value == null ? 'Choose' : formatApiDate(value),
              placeholder: value == null,
              trailingIcon: Icons.calendar_today_outlined,
              onTap: () async {
                final d = await pickDate(context, value ?? fallback);
                if (d != null) setState(() => onPicked(d));
              },
            ),
          ),
        );

    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Row(children: [
            Expanded(child: Text('ROSTER ACTION', style: condensed(30, weight: FontWeight.w800, color: p.label, height: 1))),
            IconButton(
              tooltip: 'Close',
              style: IconButton.styleFrom(backgroundColor: p.raised),
              onPressed: () => Navigator.pop(context),
              icon: const Icon(Icons.close_rounded, size: 20),
            ),
          ]),
          const SizedBox(height: 16),
          SegmentedPills<String>(
            value: _type,
            options: const {'transfer': 'Transfer', 'loan': 'Loan', 'release': 'Release'},
            onChanged: (v) => setState(() {
              _type = v;
              _error = null;
            }),
          ),
          const SizedBox(height: 16),
          LabeledField(
            label: 'Player',
            child: PickerField(
              leading: _player == null
                  ? null
                  : PlayerAvatar(playerId: _player!.playerId, name: _player!.name, clubId: widget.club.clubId, size: 32),
              text: _player?.name ?? 'Choose a player',
              detail: _player?.position,
              placeholder: _player == null,
              onTap: _choosePlayer,
            ),
          ),
          if (!isRelease) ...[
            const SizedBox(height: 14),
            LabeledField(
              label: 'To club',
              child: squads == null
                  ? const PickerField(text: 'Choose a player first', placeholder: true)
                  : squads.when(
                      loading: () => const PickerField(text: 'Loading clubs…', placeholder: true),
                      error: (_, _) => const PickerField(text: 'Clubs need a connection the first time', placeholder: true),
                      data: (list) {
                        final s = list.where((s) => s['squad_id'] == _toSquad).firstOrNull;
                        return PickerField(
                          leading: s == null ? null : TeamCrest(teamId: '${s['club_id'] ?? s['squad_id']}', name: '${s['name']}', size: 28),
                          text: s == null ? 'Choose a club' : '${s['name']}',
                          placeholder: s == null,
                          onTap: () => _chooseSquad(list),
                        );
                      },
                    ),
            ),
          ],
          const SizedBox(height: 14),
          Row(children: [
            dateField(isRelease ? 'Date' : 'Starts', _effective, (d) => _effective = d, DateTime.now()),
            if (_type == 'loan') ...[
              const SizedBox(width: 10),
              dateField('Ends', _loanEnd, (d) => _loanEnd = d, _effective.add(const Duration(days: 30))),
            ],
          ]),
          const SizedBox(height: 14),
          LabeledField(
            label: 'Reason',
            child: TextField(
              controller: _reason,
              textCapitalization: TextCapitalization.sentences,
              style: const TextStyle(fontSize: 16),
              decoration: InputDecoration(hintText: 'For the audit trail', fillColor: p.canvas),
            ),
          ),
          const SizedBox(height: 12),
          Text(
            offline
                ? 'You’re offline. It’s saved to your sync queue and sent when you reconnect.'
                : 'No connection? It’s saved to your sync queue and sent later.',
            style: TextStyle(fontSize: 13, color: offline ? p.warning : p.label2, height: 1.4),
          ),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(top: 10),
              child: Row(children: [
                Icon(Icons.error_rounded, size: 18, color: p.danger, semanticLabel: 'Error'),
                const SizedBox(width: 8),
                Expanded(child: Text(_error!, style: TextStyle(fontSize: 14, color: p.dangerSoft))),
              ]),
            ),
          const SizedBox(height: 16),
          PrimaryButton(label: 'Confirm ${humanize(_type).toLowerCase()}', onPressed: _submit),
          if (_player != null)
            TextButton(
              onPressed: () => showModalBottomSheet<void>(
                context: context,
                isScrollControlled: true,
                useSafeArea: true,
                builder: (_) => PlayerHistorySheet(player: _player!),
              ),
              child: Text('VIEW ${_player!.name.toUpperCase()}’S HISTORY'),
            ),
        ]),
      ),
    );
  }
}

/// The player's immutable roster audit trail (newest first).
class PlayerHistorySheet extends ConsumerWidget {
  final RosterPlayer player;
  const PlayerHistorySheet({super.key, required this.player});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final p = context.palette;
    final history = ref.watch(rosterHistoryProvider(player.playerId));
    final squads = player.leagueId == null ? null : ref.watch(squadsProvider(player.leagueId!)).value;
    final names = {for (final s in squads ?? const <Map<String, dynamic>>[]) s['squad_id']: '${s['name']}'};
    String squad(String? id) => id == null ? 'No squad' : (names[id] ?? id);
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Text('${player.name}: history'.toUpperCase(), style: condensed(28, weight: FontWeight.w800, color: p.label)),
        const SizedBox(height: 12),
        history.when(
          loading: () => const Padding(padding: EdgeInsets.all(24), child: LoadingView()),
          error: (e, _) => ErrorView(
            message: friendlyError(e),
            onRetry: () => ref.invalidate(rosterHistoryProvider(player.playerId)),
          ),
          data: (h) => h.entries.isEmpty
              ? Text('No moves yet.', style: TextStyle(color: p.label3))
              : Column(children: [
                  for (final e in h.entries.reversed)
                    Container(
                      padding: const EdgeInsets.symmetric(vertical: 12),
                      decoration: BoxDecoration(border: Border(bottom: BorderSide(color: p.hairline))),
                      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Expanded(
                          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                            Text(humanize(e.action).toUpperCase(), style: condensed(16, weight: FontWeight.w700, tracking: 1, color: p.label)),
                            Text(
                              [
                                if (e.fromSquadId != null || e.toSquadId != null) '${squad(e.fromSquadId)} → ${squad(e.toSquadId)}',
                                if ((e.why ?? '').isNotEmpty) e.why!,
                                'by ${e.who}',
                              ].join('\n'),
                              style: TextStyle(fontSize: 13, color: p.label3, height: 1.4),
                            ),
                          ]),
                        ),
                        Text(e.effectiveDate, style: TextStyle(fontSize: 14, color: p.label2, fontFeatures: tabular)),
                      ]),
                    ),
                  const SizedBox(height: 10),
                  Text('Every change is recorded and never edited.', style: TextStyle(fontSize: 13, color: p.label3)),
                ]),
        ),
      ]),
    );
  }
}
