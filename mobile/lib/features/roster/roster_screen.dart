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
import '../../widgets/ui.dart';
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
        body: const EmptyState(message: 'Only club managers can manage a roster.', icon: Icons.lock_rounded),
      );
    }
    final club = ref.watch(clubProvider(clubId));
    return Scaffold(
      appBar: AppBar(title: const Text('Roster')),
      body: AsyncView<Club>(
        value: club,
        onRetry: () => ref.invalidate(clubProvider(clubId)),
        isEmpty: (c) => c.roster.isEmpty,
        emptyMessage: 'No players in your squad yet',
        builder: (c) => RefreshIndicator.adaptive(
          onRefresh: () => ref.refresh(clubProvider(clubId).future),
          child: ListView(padding: const EdgeInsets.only(top: 12, bottom: 24), children: [
            Section(
              header: c.name,
              footer: 'Tap a player to transfer, loan or release them. Offline changes are saved and sync later.',
              children: [
                for (final p in c.roster)
                  InkWell(
                    onTap: () => _chooseAction(context, ref, session, p),
                    child: PlayerTile(
                      player: p,
                      trailing: Row(mainAxisSize: MainAxisSize.min, children: [
                        Text(p.position, style: Theme.of(context).textTheme.bodyLarge!.copyWith(color: context.palette.secondaryLabel)),
                        const SizedBox(width: 4),
                        Icon(Icons.more_horiz_rounded, color: context.palette.accent, semanticLabel: 'Actions for ${p.name}'),
                      ]),
                    ),
                  ),
              ],
            ),
          ]),
        ),
      ),
    );
  }

  Future<void> _chooseAction(BuildContext context, WidgetRef ref, Session session, RosterPlayer player) async {
    final type = await showCupertinoModalPopup<String>(
      context: context,
      builder: (ctx) => CupertinoActionSheet(
        title: Text(player.name),
        message: Text('${humanize(player.role)}, ${player.position}'),
        actions: [
          CupertinoActionSheetAction(onPressed: () => Navigator.pop(ctx, 'transfer'), child: const Text('Transfer')),
          CupertinoActionSheetAction(onPressed: () => Navigator.pop(ctx, 'loan'), child: const Text('Loan')),
          CupertinoActionSheetAction(
            isDestructiveAction: true,
            onPressed: () => Navigator.pop(ctx, 'release'),
            child: const Text('Release'),
          ),
        ],
        cancelButton: CupertinoActionSheetAction(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
      ),
    );
    if (type != null && context.mounted) await _startAction(context, ref, session, player, type);
  }

  Future<void> _startAction(BuildContext context, WidgetRef ref, Session session, RosterPlayer player, String type) async {
    final leagueId = session.user.leagueId ?? ref.read(selectedLeagueProvider) ?? '';
    final body = await showModalBottomSheet<Map<String, dynamic>>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
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
          ? '${player.name} will leave the squad. This can’t be undone here.'
          : '${player.name} moves on ${body['effective_date']}.',
      confirmLabel: verb,
      destructive: type == 'release',
    );
    if (!ok || !context.mounted) return;

    final sync = ref.read(syncProvider.notifier);
    if (ref.read(syncProvider).isOffline) {
      // TODO(data layer): base_version = the player's audit entry count from cached roster history.
      await sync.enqueue(type: 'roster_transfer', baseVersion: 0, payload: body);
      if (context.mounted) showSuccess(context, 'Saved. It will sync when you’re back online.');
      return;
    }
    try {
      await ref.read(repositoryProvider).rosterTransfer(body);
      ref.invalidate(clubProvider(session.user.clubId!));
      if (context.mounted) showSuccess(context, '${player.name}: $verb complete.');
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

  void _submit() {
    final isRelease = widget.type == 'release';
    final isLoan = widget.type == 'loan';
    String? error;
    if (!isRelease && _toSquad == null) error = 'Choose where the player is going.';
    if (isLoan && (_loanEnd == null || !_loanEnd!.isAfter(_effective))) error = 'The loan must end after it starts.';
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
    final t = Theme.of(context).textTheme;
    final p = context.palette;

    Widget dateRow(String label, DateTime? value, ValueChanged<DateTime> onPicked, DateTime fallback) => ListTile(
          title: Text(label),
          trailing: Text(value == null ? 'Choose' : formatApiDate(value),
              style: t.bodyLarge!.copyWith(color: p.accent, fontFeatures: tabular)),
          onTap: () async {
            final d = await pickDate(context, value ?? fallback);
            if (d != null) onPicked(d);
          },
        );

    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
      child: SingleChildScrollView(
        padding: const EdgeInsets.only(bottom: 16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(32, 0, 32, 20),
            child: Text('${humanize(widget.type)} ${widget.player.name}', style: t.headlineSmall),
          ),
          if (!isRelease)
            squads.when(
              loading: () => const Padding(padding: EdgeInsets.all(24), child: LoadingView()),
              error: (e, _) => const Section(children: [ListTile(title: Text("Couldn't load squads."))]),
              data: (list) => Section(header: 'To', children: [
                for (final s in list.where((s) => s['squad_id'] != widget.player.squadId))
                  ListTile(
                    title: Text('${s['name']}'),
                    trailing: _toSquad == s['squad_id']
                        ? Icon(Icons.check_rounded, color: p.accent, semanticLabel: 'Selected')
                        : null,
                    onTap: () => setState(() => _toSquad = s['squad_id'] as String),
                  ),
              ]),
            ),
          Section(header: 'When', children: [
            dateRow(isRelease ? 'Date' : 'Starts', _effective, (d) => setState(() => _effective = d), DateTime.now()),
            if (widget.type == 'loan')
              dateRow('Ends', _loanEnd, (d) => setState(() => _loanEnd = d), _effective.add(const Duration(days: 30))),
          ]),
          Section(header: 'Reason', children: [
            TextField(
              controller: _reason,
              textCapitalization: TextCapitalization.sentences,
              decoration: const InputDecoration(
                hintText: 'For the audit trail',
                filled: false,
                border: InputBorder.none,
                enabledBorder: InputBorder.none,
                focusedBorder: InputBorder.none,
              ),
            ),
          ]),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.fromLTRB(32, 0, 32, 16),
              child: Row(children: [
                Icon(Icons.error_rounded, size: 18, color: p.danger, semanticLabel: 'Error'),
                const SizedBox(width: 8),
                Expanded(child: Text(_error!, style: t.bodyMedium!.copyWith(color: p.danger))),
              ]),
            ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: PrimaryButton(label: 'Continue', onPressed: _submit),
          ),
          const SizedBox(height: 4),
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
        ]),
      ),
    );
  }
}
