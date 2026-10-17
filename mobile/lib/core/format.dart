/// Minor units to "PKR 4500.00" (2 decimals, no thousands separator, same as the receipt).
String formatMoney(int minor, {String currency = 'PKR'}) =>
    '$currency ${(minor / 100).toStringAsFixed(2)}';

const _weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const _months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

String _two(int n) => n.toString().padLeft(2, '0');

/// ISO-8601 string to "Sat 17 Oct, 14:00" in local time.
String formatDateTime(String? iso) {
  final dt = iso == null ? null : DateTime.tryParse(iso)?.toLocal();
  if (dt == null) return 'Time to be confirmed';
  return '${_weekdays[dt.weekday - 1]} ${dt.day} ${_months[dt.month - 1]}, ${_two(dt.hour)}:${_two(dt.minute)}';
}

/// Date to "YYYY-MM-DD" (API date format).
String formatApiDate(DateTime d) => '${d.year}-${_two(d.month)}-${_two(d.day)}';

/// Current UTC time as "YYYY-MM-DDTHH:MM:SSZ" (§7.11 queued_at format).
String nowUtcIso() {
  final d = DateTime.now().toUtc();
  return '${formatApiDate(d)}T${_two(d.hour)}:${_two(d.minute)}:${_two(d.second)}Z';
}

/// "event_type" / "in_progress" to "Event type" / "In progress".
String humanize(String raw) {
  final s = raw.replaceAll('_', ' ');
  return s.isEmpty ? s : s[0].toUpperCase() + s.substring(1);
}
