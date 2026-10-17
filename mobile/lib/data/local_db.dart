import 'dart:convert';

import 'package:path/path.dart' as p;
import 'package:sqflite/sqflite.dart';

import 'models.dart';

/// On-device SQLite (NFR-4).
///  - cache: last good response per screen (fixtures, standings, clubs, ...), readable offline.
///  - pending_actions: the offline queue in the exact §7.11 shape, plus the last sync result.
///    Rows are written BEFORE the UI says "pending", so they survive a force-close.
class LocalDb {
  LocalDb._();

  static Database? _db;

  static Future<Database> _open() async {
    if (_db != null) return _db!;
    final path = p.join(await getDatabasesPath(), 'nascon_app.db');
    return _db = await openDatabase(path, version: 1, onCreate: (db, _) async {
      await db.execute('CREATE TABLE cache (key TEXT PRIMARY KEY, json TEXT NOT NULL, updated_at TEXT NOT NULL)');
      await db.execute('CREATE TABLE pending_actions ('
          'action_id TEXT PRIMARY KEY, type TEXT NOT NULL, queued_at TEXT NOT NULL, base_version INTEGER NOT NULL, '
          'payload_json TEXT NOT NULL, status TEXT NOT NULL, error_code TEXT, seq INTEGER NOT NULL)');
    });
  }

  // ---- cache ----

  static Future<void> putCache(String key, Object? json) async {
    final db = await _open();
    await db.insert('cache', {'key': key, 'json': jsonEncode(json), 'updated_at': DateTime.now().toUtc().toIso8601String()},
        conflictAlgorithm: ConflictAlgorithm.replace);
  }

  static Future<Object?> getCache(String key) async {
    final db = await _open();
    final rows = await db.query('cache', where: 'key = ?', whereArgs: [key], limit: 1);
    return rows.isEmpty ? null : jsonDecode(rows.first['json'] as String);
  }

  // ---- offline queue ----

  static Future<void> saveAction(PendingAction a) async {
    final db = await _open();
    final seq = Sqflite.firstIntValue(await db.rawQuery('SELECT COALESCE(MAX(seq), 0) + 1 FROM pending_actions'))!;
    await db.insert(
      'pending_actions',
      {
        'action_id': a.actionId,
        'type': a.type,
        'queued_at': a.queuedAt,
        'base_version': a.baseVersion,
        'payload_json': jsonEncode(a.payload),
        'status': a.status,
        'error_code': a.errorCode,
        'seq': seq,
      },
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  static Future<void> updateStatus(String actionId, String status, String? errorCode) async {
    final db = await _open();
    await db.update('pending_actions', {'status': status, 'error_code': errorCode},
        where: 'action_id = ?', whereArgs: [actionId]);
  }

  static Future<void> deleteAction(String actionId) async {
    final db = await _open();
    await db.delete('pending_actions', where: 'action_id = ?', whereArgs: [actionId]);
  }

  /// All queued and finished-but-not-dismissed actions, oldest first.
  static Future<List<PendingAction>> loadActions() async {
    final db = await _open();
    final rows = await db.query('pending_actions', orderBy: 'seq');
    return [
      for (final r in rows)
        PendingAction(
          actionId: r['action_id'] as String,
          type: r['type'] as String,
          queuedAt: r['queued_at'] as String,
          baseVersion: r['base_version'] as int,
          payload: Map<String, dynamic>.from(jsonDecode(r['payload_json'] as String)),
          status: r['status'] as String,
          errorCode: r['error_code'] as String?,
        ),
    ];
  }
}
