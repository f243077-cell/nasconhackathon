import 'package:shared_preferences/shared_preferences.dart';

/// Server URL, changeable from the Settings screen (stored in shared prefs, never the JWT).
class ServerConfig {
  static const String defaultUrl = 'http://10.0.2.2:8080';
  static const String _key = 'server_url';

  static Future<String> load() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_key) ?? defaultUrl;
  }

  static Future<void> save(String url) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_key, url.trim().replaceAll(RegExp(r'/+$'), ''));
  }
}
