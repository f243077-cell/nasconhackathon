import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/models.dart';
import '../data/repository.dart';

/// The signed-in user. null = signed out (router sends you to /login).
// TODO(data layer): persist token + device_id with flutter_secure_storage (Keystore). Never shared prefs.
class SessionController extends Notifier<Session?> {
  @override
  Session? build() => null;

  Future<void> login(String email, String password) async {
    state = await ref.read(repositoryProvider).login(email, password);
  }

  void logout() => state = null;
}

final sessionProvider = NotifierProvider<SessionController, Session?>(SessionController.new);
