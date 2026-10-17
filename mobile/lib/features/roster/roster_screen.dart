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
import '../club/club_screen.dart';

/// Club Manager only: transfer, loan or release a player. Queued when offline.
class RosterScreen extends ConsumerWidget {
  const RosterScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(sessionProvider);
    final clubId = session?.user.clubId;
    if (session == null || !session.canManageRoster || clubId == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Roster')),
        body: const EmptyState(message: 'Only club managers can manage a roster.', icon: Icons.lock_outline),
      );
    }
    final club = ref.watch(clubProvider(clubId));
    return Scaffold(
      appBar: AppBar(title: const Text('Roster management')),
      body: AsyncView<Club>(
        value: club,
        onRetry: () => ref.invalidate(clubProvider(clubId)),
        isEmpty: (c) => c.roster.isEmpty,
        emptyMessage: 'No players in your squad yet',
        builder: (c) => RefreshIndicator(
          onRefresh: () => ref.refresh(clubProvider(clubId).future),
          child: ListView(children: [
            const Padding(
              padding: EdgeInsets.all(16),
              child: Text('Tap the menu next to a player to transfer, loan or release them.'),
            ),
            for (final p in c.roster)
              PlayerTile(
                player: p,
                trailing: PopupMenuButton<String>(
                  tooltip: 'Actions for ${p.name}',
                  onSelected: (type) => _startAction(context, ref, session, p, type),
                  itemBuilder: (_) => const [
                    PopupMenuItem(value: 'transfer', child: Text('Transfer')),
                    PopupMenuItem(value: 'loan', child: Text('Loan')),
                    PopupMenuItem(value: 'release', child: Text('Release')),
                  ],
                ),
              ),
          ]),
        ),
      ),
    );
  }

  Future<void> _startAction(BuildContext context, WidgetRef ref, Session session, RosterPlayer player, String type) async {
    final leagueId = session.user.leagueId ?? ref.read(selectedLeagueProvider) ?? '';
    final body = await showModalBottomSheet<Map<String, dynamic>>(
      context: context,
      isScrollControlled: true,
      builder: (_) => RosterActionSheet(
        player: player,
        type: type,
        leagueId: leagueId,
        requestedBy: session.user.id,
      ),
    );
    if (body == null || !context.mounted) return;

    final verb = humanize(type);
    final ok = await confirmAction(
      context,
      title: '$verb ${player.name}?',
      message: type == 'release'
          ? '${player.name} will leave the squad. This cannot be undone here.'
          : '${player.name} will move on ${body['effective_date']}.',
      confirmLabel: verb,
      destructive: type == 'release',
    );
    if (!ok || !context.mounted) return;

    final sync = ref.read(syncProvider.notifier);
    if (ref.read(syncProvider).isOffline) {
      // TODO(data layer): base_version = the player's audit entry count from cached roster history.
      await sync.enqueue(type: 'roster_transfer', baseVersion: 0, payload: body);
      if (context.mounted) showSuccess(context, "Saved as pending. It will sync when you're back online.");
      return;
    }
    try {
      await ref.read(repositoryProvider).rosterTransfer(body);
      ref.invalidate(clubProvider(session.user.clubId!));
      if (context.mounted) showSuccess(context, '$verb done for ${player.name}.');
    } catch (e) {
      if (context.mounted) showError(context, e);
    }
  }
}

/// Bottom-sheet form. Pops with the exact §7.8 transfer body, or null on cancel.
class RosterActionSheet extends ConsumerStatefulWidget {
  final RosterPlayer player;
  final String type; // transfer | loan | release
  final String leagueId;
  final String requestedBy;
  const RosterActionSheet({super.key, required this.player, required this.type, required this.leagueId, required this.requestedBy});

  @override
  ConsumerState<RosterActionSheet> createState() => _RosterActionSheetState();
}

class _RosterActionSheetState extends ConsumerState<RosterActionSheet> {
  final _reason = TextEditingController();
  String? _toSquad;
  DateTime _effective = DateTime.now();
  DateTime? _loanEnd;
  String? _error;

  @override
  void dispose() {
    _reason.dispose();
    super.dispose();
  }

  Future<DateTime?> _pickDate(DateTime initial) => showDatePicker(
        context: context,
        initialDate: initial,
        firstDate: DateTime(2020),
        lastDate: DateTime(2035),
      );

  void _submit() {
    final isRelease = widget.type == 'release';
    final isLoan = widget.type == 'loan';
    String? error;
    if (!isRelease && _toSquad == null) error = 'Choose the destination squad.';
    if (isLoan && (_loanEnd == null || !_loanEnd!.isAfter(_effective))) error = 'Loan end date must be after the start date.';
    if (_reason.text.trim().isEmpty) error = 'Add a short reason.';
    if (error != null) {
      setState(() => _error = error);
      return;
    }
    Navigator.pop(context, {
      'request_id': 'tr-${const Uuid().v4()}',
      'league_id': widget.leagueId,
      'player_id': widget.player.playerId,
      'type': widget.type,
      'from_squad_id': widget.player.squadId,
      'to_squad_id': isRelease ? null : _toSquad,
      'effective_date': formatApiDate(_effective),
      if (isLoan) 'loan_end_date': formatApiDate(_loanEnd!),
      'reason': _reason.text.trim(),
      'requested_by': widget.requestedBy,
    });
  }

  @override
  Widget build(BuildContext context) {
    final squads = ref.watch(squadsProvider(widget.leagueId));
    final isRelease = widget.type == 'release';
    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
      child: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Text('${humanize(widget.type)} ${widget.player.name}', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 16),
            if (!isRelease)
              squads.when(
                loading: () => const LinearProgressIndicator(),
                error: (e, _) => const Text("Couldn't load squads."),
                data: (list) => DropdownButtonFormField<String>(
                  initialValue: _toSquad,
                  isExpanded: true,
                  decoration: const InputDecoration(labelText: 'To squad'),
                  items: [
                    for (final s in list.where((s) => s['squad_id'] != widget.player.squadId))
                      DropdownMenuItem(value: s['squad_id'] as String, child: Text('${s['name']}')),
                  ],
                  onChanged: (v) => setState(() => _toSquad = v),
                ),
              ),
            const SizedBox(height: 12),
            OutlinedButton.icon(
              icon: const Icon(Icons.event),
              label: Text('Effective date: ${formatApiDate(_effective)}'),
              onPressed: () async {
                final d = await _pickDate(_effective);
                if (d != null) setState(() => _effective = d);
              },
            ),
            if (widget.type == 'loan') ...[
              const SizedBox(height: 12),
              OutlinedButton.icon(
                icon: const Icon(Icons.event_available),
                label: Text('Loan ends: ${_loanEnd == null ? 'choose date' : formatApiDate(_loanEnd!)}'),
                onPressed: () async {
                  final d = await _pickDate(_loanEnd ?? _effective.add(const Duration(days: 30)));
                  if (d != null) setState(() => _loanEnd = d);
                },
              ),
            ],
            const SizedBox(height: 12),
            TextField(controller: _reason, decoration: const InputDecoration(labelText: 'Reason')),
            if (_error != null) ...[
              const SizedBox(height: 8),
              Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
            ],
            const SizedBox(height: 16),
            FilledButton(onPressed: _submit, child: const Text('Continue')),
            TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
          ]),
        ),
      ),
    );
  }
}
