import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/errors.dart';
import '../../core/session.dart';
import '../../core/theme.dart';
import '../../widgets/tenant_title.dart';
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
      // Router redirect takes the user to their role-aware home.
    } catch (e) {
      if (mounted) setState(() => _error = friendlyError(e));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    final t = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(
        actions: [
          IconButton(
            tooltip: 'Server settings',
            icon: const Icon(Icons.dns_rounded),
            onPressed: () => context.push('/settings'),
          ),
        ],
      ),
      body: SafeArea(
        top: false,
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 440),
            child: ListView(
              padding: const EdgeInsets.fromLTRB(0, 8, 0, 24),
              children: [
                const Padding(
                  padding: EdgeInsets.symmetric(horizontal: 32),
                  child: Align(alignment: Alignment.centerLeft, child: TenantMark(size: 56)),
                ),
                const SizedBox(height: 20),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 32),
                  child: Text('Sign In', style: t.headlineLarge),
                ),
                const SizedBox(height: 6),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 32),
                  child: Text('Fixtures, scores, standings and the club store.', style: t.bodyMedium),
                ),
                const SizedBox(height: 28),
                Section(children: [
                  _Field(
                    controller: _email,
                    label: 'Email',
                    keyboardType: TextInputType.emailAddress,
                    autofillHints: const [AutofillHints.email],
                    textInputAction: TextInputAction.next,
                  ),
                  _Field(
                    controller: _password,
                    label: 'Password',
                    obscureText: _obscure,
                    autofillHints: const [AutofillHints.password],
                    onSubmitted: (_) => _submit(),
                    suffix: IconButton(
                      tooltip: _obscure ? 'Show password' : 'Hide password',
                      icon: Icon(_obscure ? Icons.visibility_rounded : Icons.visibility_off_rounded, color: p.secondaryLabel),
                      onPressed: () => setState(() => _obscure = !_obscure),
                    ),
                  ),
                ]),
                AnimatedSize(
                  duration: MediaQuery.of(context).disableAnimations ? Duration.zero : const Duration(milliseconds: 200),
                  child: _error == null
                      ? const SizedBox(width: double.infinity)
                      : Padding(
                          padding: const EdgeInsets.fromLTRB(32, 0, 32, 20),
                          child: Row(children: [
                            Icon(Icons.error_rounded, size: 18, color: p.danger, semanticLabel: 'Error'),
                            const SizedBox(width: 8),
                            Expanded(child: Text(_error!, style: t.bodyMedium!.copyWith(color: p.danger))),
                          ]),
                        ),
                ),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: PrimaryButton(label: 'Sign In', loading: _loading, onPressed: _submit),
                ),
                const SizedBox(height: 32),
                // Seeded accounts (backend/app/seed/baseline.json), shown for judges and testing.
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 32),
                  child: Text(
                    'Demo accounts, password Nascon@26:\norganizer@nascon.test\nmanager@nascon.test\n'
                    'player@nascon.test\nviewer@nascon.test\nadmin@nascon.test',
                    style: t.bodySmall,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Borderless text field that sits inside a grouped [Section] row.
class _Field extends StatelessWidget {
  final TextEditingController controller;
  final String label;
  final bool obscureText;
  final TextInputType? keyboardType;
  final Iterable<String>? autofillHints;
  final TextInputAction? textInputAction;
  final ValueChanged<String>? onSubmitted;
  final Widget? suffix;

  const _Field({
    required this.controller,
    required this.label,
    this.obscureText = false,
    this.keyboardType,
    this.autofillHints,
    this.textInputAction,
    this.onSubmitted,
    this.suffix,
  });

  @override
  Widget build(BuildContext context) => TextField(
        controller: controller,
        obscureText: obscureText,
        keyboardType: keyboardType,
        autofillHints: autofillHints,
        textInputAction: textInputAction,
        onSubmitted: onSubmitted,
        style: Theme.of(context).textTheme.bodyLarge,
        decoration: InputDecoration(
          labelText: label,
          filled: false,
          border: InputBorder.none,
          enabledBorder: InputBorder.none,
          focusedBorder: InputBorder.none,
          suffixIcon: suffix,
        ),
      );
}
