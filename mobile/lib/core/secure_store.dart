import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:uuid/uuid.dart';

/// Android Keystore-backed storage for the JWT, the signed-in session and the device id
/// (NFR-5). Never shared prefs or SQLite.
class SecureStore {
  SecureStore._();

  static const _storage = FlutterSecureStorage();
  static const _sessionKey = 'session_json';
  static const _deviceKey = 'device_id';

  /// In-memory copy so every request does not hit the Keystore.
  static String? token;
  static String? _deviceId;

  static Future<void> saveSession(Map<String, dynamic> sessionJson) async {
    token = sessionJson['token'] as String?;
    await _storage.write(key: _sessionKey, value: jsonEncode(sessionJson));
  }

  static Future<Map<String, dynamic>?> loadSession() async {
    final raw = await _storage.read(key: _sessionKey);
    if (raw == null) return null;
    final json = Map<String, dynamic>.from(jsonDecode(raw));
    token = json['token'] as String?;
    return json;
  }

  static Future<void> clearSession() async {
    token = null;
    await _storage.delete(key: _sessionKey);
  }

  /// Generated once per install and kept for every offline-sync request.
  static Future<String> deviceId() async {
    if (_deviceId != null) return _deviceId!;
    var id = await _storage.read(key: _deviceKey);
    if (id == null) {
      id = 'dev-${const Uuid().v4()}';
      await _storage.write(key: _deviceKey, value: id);
    }
    return _deviceId = id;
  }
}
