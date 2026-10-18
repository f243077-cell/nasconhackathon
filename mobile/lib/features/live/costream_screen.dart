import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/config.dart';
import '../../core/errors.dart';
import '../../core/session.dart';
import '../../core/theme.dart';
import '../../widgets/async_view.dart';
import '../../widgets/team_crest.dart';
import '../../widgets/ui.dart';
import 'live_feed.dart';

/// Co-Stream (deep link nascon://stream/cs-session-*). Composite playback + the session's single
/// chat room `chat-{session_id}`. Guests read; posting needs an account (server returns 403 for guests).
class CoStreamScreen extends ConsumerStatefulWidget {
  final String sessionId;
  const CoStreamScreen({super.key, required this.sessionId});

  @override
  ConsumerState<CoStreamScreen> createState() => _CoStreamScreenState();
}

class _CoStreamScreenState extends ConsumerState<CoStreamScreen> {
  final _input = TextEditingController();
  final _local = <ChatMessage>[];
  bool _sending = false;
  String? _playback;

  String get _room => 'chat-${widget.sessionId}';

  @override
  void initState() {
    super.initState();
    ServerConfig.load().then((base) {
      final host = Uri.parse(base).host;
      if (mounted) setState(() => _playback = 'http://$host:8888/costream/${widget.sessionId}/index.m3u8');
    });
  }

  @override
  void dispose() {
    _input.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    final text = _input.text.trim();
    if (text.isEmpty) return;
    if (ref.read(sessionProvider) == null) {
      _askToSignIn();
      return;
    }
    setState(() => _sending = true);
    try {
      final msg = await sendChat(_room, text);
      _input.clear();
      if (msg != null) setState(() => _local.add(msg));
    } on ApiException catch (e) {
      if (!mounted) return;
      if (e.code == 'GUEST_WRITE_FORBIDDEN' || e.code == 'UNAUTHENTICATED') {
        _askToSignIn();
      } else {
        showError(context, e);
      }
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  void _askToSignIn() {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(
        content: const Text('Sign in to chat. You can keep watching as a guest.'),
        action: SnackBarAction(label: 'SIGN IN', onPressed: () => context.go('/login')),
      ));
  }

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    final signedIn = ref.watch(sessionProvider) != null;
    final chat = ref.watch(chatProvider(_room));
    final server = chat.value ?? const <ChatMessage>[];
    final keys = {for (final m in server) m.key};
    final messages = [...server, ..._local.where((m) => !keys.contains(m.key))];

    return Semantics(
      identifier: 'costream-screen',
      container: true,
      label: 'Co-stream',
      child: FlatPage(
        title: 'Co-Stream',
        backFallback: signedIn ? '/fixtures' : '/login',
        children: [
          Panel(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                LiveDot(color: p.live, size: 8),
                const SizedBox(width: 8),
                Text('LIVE', style: condensed(14, weight: FontWeight.w800, tracking: 1.5, color: p.live)),
                const Spacer(),
                Tag(widget.sessionId, color: p.raised, textColor: p.label2),
              ]),
              const SizedBox(height: 14),
              AspectRatio(
                aspectRatio: 16 / 9,
                child: DecoratedBox(
                  decoration: BoxDecoration(color: Colors.black, borderRadius: BorderRadius.circular(12)),
                  child: Center(
                    child: Column(mainAxisSize: MainAxisSize.min, children: [
                      Icon(Icons.grid_view_rounded, size: 40, color: p.accent),
                      const SizedBox(height: 10),
                      Text('Up to 4 hosts, one composite stream', style: TextStyle(color: p.label2, fontSize: 14)),
                    ]),
                  ),
                ),
              ),
              if (_playback != null) ...[
                const SizedBox(height: 12),
                InkWell(
                  onTap: () {
                    Clipboard.setData(ClipboardData(text: _playback!));
                    showSuccess(context, 'Stream link copied.');
                  },
                  child: Padding(
                    padding: const EdgeInsets.symmetric(vertical: 8),
                    child: Row(children: [
                      Icon(Icons.link_rounded, size: 18, color: p.label2),
                      const SizedBox(width: 8),
                      Expanded(child: Text(_playback!, style: TextStyle(color: p.label2, fontSize: 13), overflow: TextOverflow.ellipsis)),
                      Icon(Icons.copy_rounded, size: 18, color: p.label2, semanticLabel: 'Copy stream link'),
                    ]),
                  ),
                ),
              ],
            ]),
          ),
          const SizedBox(height: 16),
          SectionLabel('CHAT', trailing: Text(_room, style: TextStyle(color: p.label3, fontSize: 12))),
          Panel(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
            child: Semantics(
              identifier: 'chat-list',
              container: true,
              child: messages.isEmpty
                  ? Padding(
                      padding: const EdgeInsets.symmetric(vertical: 24),
                      child: Center(child: Text('No messages yet.', style: TextStyle(color: p.label2))),
                    )
                  : Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      for (final m in messages.length > 50 ? messages.sublist(messages.length - 50) : messages)
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 6),
                          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                            Text(m.sender, style: TextStyle(color: p.accent, fontWeight: FontWeight.w600, fontSize: 13)),
                            Text(m.text, style: TextStyle(color: m.flagged ? p.label2 : p.label, fontSize: 16)),
                          ]),
                        ),
                    ]),
            ),
          ),
          const SizedBox(height: 12),
          Row(children: [
            Expanded(
              child: Semantics(
                identifier: 'chat-input',
                child: TextField(
                  controller: _input,
                  maxLength: 280,
                  textInputAction: TextInputAction.send,
                  onSubmitted: (_) => _send(),
                  decoration: const InputDecoration(hintText: 'Say something', counterText: ''),
                ),
              ),
            ),
            const SizedBox(width: 10),
            Semantics(
              identifier: 'chat-send',
              child: SizedBox(
                width: 96,
                child: PrimaryButton(label: 'SEND', loading: _sending, onPressed: _send, height: 52),
              ),
            ),
          ]),
          if (!signedIn) ...[
            const SizedBox(height: 10),
            Text('Watching as guest. Sign in to post.', style: TextStyle(color: p.label2, fontSize: 13)),
          ],
        ],
      ),
    );
  }
}
