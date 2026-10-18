import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/errors.dart';
import '../../core/session.dart';
import '../../core/theme.dart';
import '../../widgets/async_view.dart';
import '../../widgets/confirm_dialog.dart';
import '../../widgets/ui.dart';
import 'live_feed.dart';

/// Who is on air, and the host's controls (FR-3.3): invite, mute/unmute, spotlight, kick, leave.
/// Invited players can join with their token. Guests only see the list.
class CoStreamParticipants extends ConsumerStatefulWidget {
  final String sessionId;
  final CoStreamSession? session;
  const CoStreamParticipants({super.key, required this.sessionId, required this.session});

  @override
  ConsumerState<CoStreamParticipants> createState() => _CoStreamParticipantsState();
}

class _CoStreamParticipantsState extends ConsumerState<CoStreamParticipants> {
  final _inviteFor = TextEditingController();
  final _token = TextEditingController();
  bool _busy = false;

  @override
  void dispose() {
    _inviteFor.dispose();
    _token.dispose();
    super.dispose();
  }

  Future<void> _act(Future<void> Function() call, String done) async {
    setState(() => _busy = true);
    try {
      await call();
      ref.invalidate(coStreamProvider(widget.sessionId));
      if (mounted) showSuccess(context, done);
    } on ApiException catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _invite() async {
    final id = _inviteFor.text.trim();
    if (id.isEmpty) return;
    setState(() => _busy = true);
    try {
      final token = await CoStreamApi.invite(widget.sessionId, id);
      _inviteFor.clear();
      if (token != null) await Clipboard.setData(ClipboardData(text: token));
      if (mounted) showSuccess(context, 'Invite sent to ${prettyId(id)}. Token copied in case they need it.');
    } on ApiException catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _control(String action, String id) async {
    final who = prettyId(id);
    switch (action) {
      case 'mute':
        await _act(() => CoStreamApi.mute(widget.sessionId, id, muted: true), '$who muted.');
      case 'unmute':
        await _act(() => CoStreamApi.mute(widget.sessionId, id, muted: false), '$who unmuted.');
      case 'spotlight':
        await _act(() => CoStreamApi.spotlight(widget.sessionId, id), '$who is in the spotlight.');
      case 'kick':
        final ok = await confirmAction(context,
            title: 'Remove $who?', message: 'They leave the co-stream right away.', confirmLabel: 'Remove', destructive: true);
        if (ok) await _act(() => CoStreamApi.kick(widget.sessionId, id), '$who removed.');
    }
  }

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    final s = widget.session;
    final me = ref.watch(sessionProvider)?.user.playerId;

    if (s == null) {
      return Panel(child: Text('Waiting for the hosts to go live.', style: TextStyle(color: p.label2, fontSize: 14)));
    }
    if (s.status != 'active') {
      return Panel(child: Text('This co-stream has ended.', style: TextStyle(color: p.label2, fontSize: 14)));
    }
    final isHost = me != null && s.host == me;
    final onAir = me != null && s.participants.contains(me);

    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      SectionLabel(
        'ON AIR',
        trailing: Text('${s.participants.length}/4, ${s.layout.replaceAll('_', ' ').toUpperCase()}',
            style: condensed(12, weight: FontWeight.w700, tracking: 1, color: p.label3)),
      ),
      Panel(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        child: Column(children: [
          for (final id in s.participants)
            Semantics(
              identifier: 'participant-$id',
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: Row(children: [
                  Icon(
                    s.muted.contains(id) ? Icons.mic_off_rounded : Icons.mic_rounded,
                    color: s.muted.contains(id) ? p.label3 : p.success,
                    size: 20,
                    semanticLabel: s.muted.contains(id) ? 'Muted' : 'Mic on',
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(prettyId(id), style: TextStyle(color: p.label, fontSize: 16, fontWeight: FontWeight.w600)),
                  ),
                  if (s.host == id) Tag('HOST', color: p.accent, textColor: p.onAccent),
                  if (s.spotlight == id) ...[const SizedBox(width: 6), Tag('SPOTLIGHT', color: p.raised, textColor: p.label)],
                  if (isHost && id != me)
                    PopupMenuButton<String>(
                      tooltip: 'Controls for ${prettyId(id)}',
                      enabled: !_busy,
                      onSelected: (a) => _control(a, id),
                      itemBuilder: (_) => [
                        PopupMenuItem(value: s.muted.contains(id) ? 'unmute' : 'mute', child: Text(s.muted.contains(id) ? 'Unmute' : 'Mute')),
                        const PopupMenuItem(value: 'spotlight', child: Text('Spotlight')),
                        const PopupMenuItem(value: 'kick', child: Text('Remove from stream')),
                      ],
                    ),
                ]),
              ),
            ),
        ]),
      ),
      if (isHost) ...[
        const SizedBox(height: 12),
        Row(children: [
          Expanded(child: TextField(controller: _inviteFor, decoration: const InputDecoration(hintText: 'Player ID to invite'))),
          const SizedBox(width: 10),
          SizedBox(
            width: 110,
            child: PrimaryButton(label: 'INVITE', loading: _busy, height: 52, onPressed: s.participants.length >= 4 ? null : _invite),
          ),
        ]),
        const SizedBox(height: 10),
        SecondaryButton(
          label: 'Leave as Host',
          icon: Icons.logout_rounded,
          destructive: true,
          onPressed: _busy
              ? null
              : () async {
                  final ok = await confirmAction(context,
                      title: 'Leave the Co-Stream?',
                      message: 'Hosting passes to the next person on air, or the stream ends.',
                      confirmLabel: 'Leave',
                      destructive: true);
                  if (ok) await _act(() => CoStreamApi.leave(widget.sessionId), 'You left. Hosting moved on.');
                },
        ),
      ] else if (me != null && !onAir) ...[
        const SizedBox(height: 12),
        Row(children: [
          Expanded(child: TextField(controller: _token, decoration: const InputDecoration(hintText: 'Invite token'))),
          const SizedBox(width: 10),
          SizedBox(
            width: 100,
            child: PrimaryButton(
              label: 'JOIN',
              loading: _busy,
              height: 52,
              onPressed: () {
                final t = _token.text.trim();
                if (t.isNotEmpty) _act(() => CoStreamApi.join(widget.sessionId, t), 'You joined the co-stream.');
              },
            ),
          ),
        ]),
      ],
    ]);
  }
}
