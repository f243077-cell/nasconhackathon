import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/models.dart';
import '../data/repository.dart';
import 'secure_store.dart';

/// The signed-in user. null = signed out (router sends you to /login).
/// Token + session live in flutter_secure_storage (Android Keystore), never shared prefs,
/// and are restored on app start so a reopened app (even offline) stays signed in.
class SessionController extends Notifier<Session?> {
  @override
  Session? build() {
    Future.microtask(_restore);
    return null;
  }

  Future<void> _restore() async {
    Map<String, dynamic>? saved;
    try {
      saved = await SecureStore.loadSession();
    } catch (_) {
      return; // unreadable keystore entry: stay signed out
    }
    if (saved != null && state == null && ref.mounted) state = Session.fromJson(saved);
  }

  Future<void> login(String email, String password) async {
    state = await ref.read(repositoryProvider).login(email, password);
  }

  Future<void> logout() async {
    await SecureStore.clearSession();
    state = null;
  }
}

final sessionProvider = NotifierProvider<SessionController, Session?>(SessionController.new);
