import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/errors.dart';
import '../../core/session.dart';
import '../../core/theme.dart';
import '../../widgets/async_view.dart';
import '../../widgets/confirm_dialog.dart';
import '../../widgets/ui.dart';
import 'live_feed.dart';

/// Broadcaster (FR-3.2): a player gets a signed stream key with RTMP (OBS / FFmpeg) and WebRTC
/// WHIP ingest URLs, can rotate it (old key stops within 2 s) or revoke it. Co-stream sessions open
/// from here too.
class BroadcastScreen extends ConsumerStatefulWidget {
  const BroadcastScreen({super.key});

  @override
  ConsumerState<BroadcastScreen> createState() => _BroadcastScreenState();
}

class _BroadcastScreenState extends ConsumerState<BroadcastScreen> {
  StreamKey? _key;
  bool _busy = false;
  bool _reveal = false;
  final _session = TextEditingController(text: 'cs-session-101');

  @override
  void dispose() {
    _session.dispose();
    super.dispose();
  }

  Future<void> _run(String action) async {
    final session = ref.read(sessionProvider);
    final playerId = session?.user.playerId;
    if (playerId == null) {
      showError(context, ApiException('FORBIDDEN'));
      return;
    }
    if (action == 'revoke') {
      final ok = await confirmAction(context,
          title: 'Revoke Stream Key?', message: 'Anyone streaming with this key is cut off within 2 seconds.', confirmLabel: 'Revoke', destructive: true);
      if (!ok) return;
    }
    setState(() => _busy = true);
    try {
      final k = await streamKeyAction(action, playerId);
      if (!mounted) return;
      setState(() {
        _key = k;
        _reveal = false;
      });
      showSuccess(context, switch (action) { 'rotate' => 'New key issued. The old one no longer works.', 'revoke' => 'Stream key revoked.', _ => 'Stream key ready.' });
    } on ApiException catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _copy(String what, String value) {
    Clipboard.setData(ClipboardData(text: value));
    showSuccess(context, '$what copied.');
  }

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    final playerId = ref.watch(sessionProvider)?.user.playerId;
    final k = _key;
    final active = k != null && k.status == 'active';

    Widget row(String label, String? value, {bool secret = false}) => Panel(
          padding: const EdgeInsets.fromLTRB(16, 12, 8, 12),
          child: Row(children: [
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(label, style: condensed(13, weight: FontWeight.w700, tracking: 1.2, color: p.label3)),
                const SizedBox(height: 4),
                Text(value == null ? 'Not available' : (secret && !_reveal ? '•' * 18 : value),
                    style: TextStyle(color: p.label, fontSize: 15), maxLines: 2, overflow: TextOverflow.ellipsis),
              ]),
            ),
            if (secret && value != null)
              IconButton(
                tooltip: _reveal ? 'Hide key' : 'Show key',
                icon: Icon(_reveal ? Icons.visibility_off_rounded : Icons.visibility_rounded),
                onPressed: () => setState(() => _reveal = !_reveal),
              ),
            if (value != null)
              IconButton(tooltip: 'Copy $label', icon: const Icon(Icons.copy_rounded), onPressed: () => _copy(label, value)),
          ]),
        );

    return Semantics(
      identifier: 'broadcast-screen',
      container: true,
      child: FlatPage(
        title: 'Go Live',
        actions: [
          PrimaryButton(
            label: active ? 'Rotate Key' : 'Get Stream Key',
            icon: active ? Icons.autorenew_rounded : Icons.key_rounded,
            loading: _busy,
            onPressed: playerId == null ? null : () => _run(active ? 'rotate' : 'generate'),
          ),
        ],
        children: [
          if (playerId == null)
            const EmptyState(message: 'Going live is for player accounts. Sign in as a player to get a stream key.', icon: Icons.videocam_off_rounded)
          else ...[
            Panel(
              child: Row(children: [
                Icon(active ? Icons.sensors_rounded : Icons.sensors_off_rounded, color: active ? p.live : p.label2, size: 28),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    k == null ? 'Get a key, paste it into OBS or any RTMP app, and start streaming.' : (active ? 'Key active. Start streaming from OBS or a WHIP app.' : 'Key revoked. Get a new one to stream again.'),
                    style: TextStyle(color: p.label, fontSize: 15),
                  ),
                ),
              ]),
            ),
            if (k != null) ...[
              const SizedBox(height: 16),
              const SectionLabel('INGEST'),
              row('STREAM KEY', k.status == 'active' ? k.streamKey : null, secret: true),
              const SizedBox(height: 8),
              row('RTMP SERVER', k.rtmp),
              const SizedBox(height: 8),
              row('WEBRTC (WHIP)', k.webrtc),
              const SizedBox(height: 8),
              row('PLAYBACK (HLS)', k.playback),
              if (active) ...[
                const SizedBox(height: 12),
                SecondaryButton(label: 'Revoke Key', icon: Icons.block_rounded, destructive: true, onPressed: _busy ? null : () => _run('revoke')),
              ],
            ],
            const SizedBox(height: 24),
            const SectionLabel('CO-STREAM'),
            Panel(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('Join a co-stream with up to 4 hosts. One shared chat room for everyone.', style: TextStyle(color: p.label2, fontSize: 14)),
                const SizedBox(height: 12),
                TextField(controller: _session, decoration: const InputDecoration(labelText: 'Session ID')),
                const SizedBox(height: 12),
                SecondaryButton(
                  label: 'Open Co-Stream',
                  icon: Icons.grid_view_rounded,
                  onPressed: () {
                    final id = _session.text.trim();
                    if (id.isNotEmpty) context.push('/costream/$id');
                  },
                ),
              ]),
            ),
          ],
        ],
      ),
    );
  }
}
