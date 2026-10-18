import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/config.dart';
import '../../core/errors.dart';
import '../../core/session.dart';
import '../../core/theme.dart';
import '../../widgets/app_logo.dart';
import '../../widgets/sync_status_bar.dart';
import '../../widgets/ui.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _email = TextEditingController();
  final _password = TextEditingController();
  bool _obscure = true;
  bool _loading = false;
  String? _error;
  String _server = ServerConfig.defaultUrl;

  @override
  void initState() {
    super.initState();
    _loadServer();
  }

  Future<void> _loadServer() async {
    final url = await ServerConfig.load();
    if (mounted) setState(() => _server = url);
  }

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_email.text.trim().isEmpty || _password.text.isEmpty) {
      setState(() => _error = 'Enter your email and password.');
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      await ref.read(sessionProvider.notifier).login(_email.text.trim(), _password.text);
      // Router redirect takes the user to Fixtures.
    } catch (e) {
      if (mounted) setState(() => _error = friendlyError(e));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    final host = _server.replaceFirst(RegExp(r'^https?://'), '');
    return Scaffold(
      body: Stack(children: [
        // Floodlit pitch fading into the night canvas.
        Positioned(
          left: 0,
          right: 0,
          top: 0,
          height: 340,
          child: Stack(fit: StackFit.expand, children: [
            Opacity(opacity: 0.6, child: PitchBackdrop(glow: p.accent)),
            DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [p.canvas.withValues(alpha: 0.35), p.canvas],
                ),
              ),
            ),
          ]),
        ),
        SafeArea(
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 440),
              child: ListView(
                padding: const EdgeInsets.fromLTRB(20, 4, 20, 24),
                children: [
                  const ScreenHeader(leading: StatusPill(linkToQueue: false)),
                  const SizedBox(height: 70),
                  const Align(alignment: Alignment.centerLeft, child: AppLogo(size: 64)),
                  const SizedBox(height: 12),
                  Semantics(
                    header: true,
                    child: Text('PLAYGRID', style: condensed(46, weight: FontWeight.w800, color: p.label, height: 0.95)),
                  ),
                  const SizedBox(height: 12),
                  Text('Sign in to follow your league.', style: TextStyle(fontSize: 16, color: p.label2)),
                  const SizedBox(height: 22),
                  AutofillGroup(
                    child: Column(children: [
                      LabeledField(
                        label: 'Email',
                        child: TextField(
                          key: const ValueKey('login-email'),
                          controller: _email,
                          keyboardType: TextInputType.emailAddress,
                          autofillHints: const [AutofillHints.email],
                          textInputAction: TextInputAction.next,
                          autocorrect: false,
                          style: const TextStyle(fontSize: 16),
                          decoration: const InputDecoration(hintText: 'you@club.test'),
                        ),
                      ),
                      const SizedBox(height: 14),
                      LabeledField(
                        label: 'Password',
                        child: TextField(
                          key: const ValueKey('login-password'),
                          controller: _password,
                          obscureText: _obscure,
                          autofillHints: const [AutofillHints.password],
                          onSubmitted: (_) => _submit(),
                          style: const TextStyle(fontSize: 16),
                          decoration: InputDecoration(
                            suffixIcon: TextButton(
                              onPressed: () => setState(() => _obscure = !_obscure),
                              child: Text(
                                _obscure ? 'Show' : 'Hide',
                                semanticsLabel: _obscure ? 'Show password' : 'Hide password',
                                style: TextStyle(fontFamily: bodyFont, fontSize: 14, fontWeight: FontWeight.w600, color: p.accent),
                              ),
                            ),
                          ),
                        ),
                      ),
                    ]),
                  ),
                  AnimatedSize(
                    duration: MediaQuery.of(context).disableAnimations ? Duration.zero : const Duration(milliseconds: 200),
                    child: _error == null
                        ? const SizedBox(width: double.infinity, height: 18)
                        : Padding(
                            padding: const EdgeInsets.symmetric(vertical: 14),
                            child: Row(children: [
                              Icon(Icons.error_rounded, size: 18, color: p.danger, semanticLabel: 'Error'),
                              const SizedBox(width: 8),
                              Expanded(child: Text(_error!, style: TextStyle(fontSize: 14, color: p.dangerSoft))),
                            ]),
                          ),
                  ),
                  Semantics(identifier: 'login-submit', child: PrimaryButton(label: 'Sign in', loading: _loading, onPressed: _submit)),
                  const SizedBox(height: 6),
                  Row(children: [
                    Expanded(
                      child: Text('Server · $host', overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 14, color: p.label2)),
                    ),
                    TextButton(
                      onPressed: () async {
                        await context.push('/settings');
                        _loadServer();
                      },
                      child: Text(
                        'Change',
                        semanticsLabel: 'Change server',
                        style: TextStyle(
                          fontFamily: bodyFont,
                          fontSize: 14,
                          fontWeight: FontWeight.w600,
                          color: p.accent,
                          decoration: TextDecoration.underline,
                          decorationColor: p.accent,
                        ),
                      ),
                    ),
                  ]),
                  const SizedBox(height: 18),
                  // Seeded accounts (backend/app/seed/baseline.json), shown for judges and testing.
                  Text(
                    'DEMO ACCOUNTS · PASSWORD Nascon@26',
                    style: condensed(12, weight: FontWeight.w600, tracking: 1, color: p.label3),
                  ),
                  const SizedBox(height: 6),
                  Wrap(spacing: 8, runSpacing: 8, children: [
                    for (final who in const ['organizer', 'manager', 'player', 'viewer', 'admin'])
                      ActionChip(
                        label: Text(who),
                        labelStyle: TextStyle(fontSize: 13, color: p.label2),
                        backgroundColor: p.surface,
                        side: BorderSide(color: p.border),
                        shape: const StadiumBorder(),
                        onPressed: () => setState(() {
                          _email.text = '$who@nascon.test';
                          _password.text = 'Nascon@26';
                          _error = null;
                        }),
                      ),
                  ]),
                ],
              ),
            ),
          ),
        ),
      ]),
    );
  }
}
