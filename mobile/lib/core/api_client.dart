import 'package:dio/dio.dart';

import 'config.dart';
import 'errors.dart';
import 'secure_store.dart';

/// Thin dio wrapper: base URL from Settings, Bearer token from [SecureStore], and every
/// failure turned into an [ApiException] whose code maps to plain text in errors.dart.
/// A request that never reaches the server becomes code OFFLINE.
class ApiClient {
  ApiClient._();

  static final Dio _dio = Dio(BaseOptions(
    connectTimeout: const Duration(seconds: 4),
    receiveTimeout: const Duration(seconds: 8),
    sendTimeout: const Duration(seconds: 8),
    contentType: 'application/json',
  ));

  static Future<String> baseUrl() => ServerConfig.load();

  static Future<dynamic> get(String path, {Map<String, dynamic>? query, Duration? timeout}) =>
      _send('GET', path, query: query, timeout: timeout);

  static Future<dynamic> post(String path, Object? body) => _send('POST', path, body: body);

  static Future<List<int>> getBytes(String path) async {
    final res = await _send('GET', path, bytes: true);
    return List<int>.from(res as List);
  }

  static Future<dynamic> _send(String method, String path,
      {Object? body, Map<String, dynamic>? query, bool bytes = false, Duration? timeout}) async {
    final base = await baseUrl();
    try {
      final res = await _dio.request(
        '$base$path',
        data: body,
        queryParameters: query,
        options: Options(
          method: method,
          headers: {if (SecureStore.token != null) 'Authorization': 'Bearer ${SecureStore.token}'},
          responseType: bytes ? ResponseType.bytes : ResponseType.json,
          receiveTimeout: timeout,
          sendTimeout: timeout,
        ),
      );
      return res.data;
    } on DioException catch (e) {
      throw _toApiException(e);
    }
  }

  static ApiException _toApiException(DioException e) {
    final res = e.response;
    if (res == null) return ApiException('OFFLINE', message: e.message);
    final data = res.data;
    if (data is Map && data['error'] is Map) {
      final err = Map<String, dynamic>.from(data['error']);
      return ApiException('${err['code']}',
          message: err['message'] as String?, details: Map<String, dynamic>.from(err['details'] ?? {}));
    }
    return ApiException(res.statusCode == 401 ? 'UNAUTHENTICATED' : 'HTTP_${res.statusCode}');
  }

  /// ws://host:port/api/v1/ws?token=... built from the same server URL.
  static Future<Uri> websocketUri() async {
    final base = Uri.parse(await baseUrl());
    return base.replace(
      scheme: base.scheme == 'https' ? 'wss' : 'ws',
      path: '/api/v1/ws',
      queryParameters: {'token': SecureStore.token ?? ''},
    );
  }
}
