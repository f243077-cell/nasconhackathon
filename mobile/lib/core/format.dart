/// Minor units to "PKR 4,500" (paisa only when there are some: "PKR 4,500.50").
String formatMoney(int minor, {String currency = 'PKR'}) {
  final negative = minor < 0;
  final abs = minor.abs();
  final whole = (abs ~/ 100).toString().replaceAllMapped(RegExp(r'\B(?=(\d{3})+(?!\d))'), (_) => ',');
  final cents = abs % 100;
  return '${negative ? '−' : ''}$currency $whole${cents == 0 ? '' : '.${_two(cents)}'}';
}

const _weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const _months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

String _two(int n) => n.toString().padLeft(2, '0');

DateTime? parseLocal(String? iso) => iso == null ? null : DateTime.tryParse(iso)?.toLocal();

/// ISO-8601 string to "Sat 17 Oct, 14:00" in local time.
String formatDateTime(String? iso) {
  final dt = parseLocal(iso);
  if (dt == null) return 'Time to be confirmed';
  return '${_weekdays[dt.weekday - 1]} ${dt.day} ${_months[dt.month - 1]}, ${_two(dt.hour)}:${_two(dt.minute)}';
}

/// "14:00" local, or "TBC".
String formatClock(String? iso) {
  final dt = parseLocal(iso);
  return dt == null ? 'TBC' : '${_two(dt.hour)}:${_two(dt.minute)}';
}

String weekdayShort(DateTime d) => _weekdays[d.weekday - 1];
String monthShort(DateTime d) => _months[d.month - 1];

/// "Sat 24" for a local date.
String formatDay(DateTime d) => '${weekdayShort(d)} ${d.day}';

/// "17 Oct, 11:52" for a local timestamp.
String formatStamp(DateTime d) => '${d.day} ${monthShort(d)}, ${_two(d.hour)}:${_two(d.minute)}';

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

/// "Karachi Kings" -> "KK", "Wolves" -> "WO".
String initialsOf(String name) {
  final words = name.split(RegExp(r'\s+')).where((w) => w.isNotEmpty && !w.endsWith('.')).toList();
  if (words.isEmpty) return '?';
  if (words.length == 1) return words.first.substring(0, words.first.length.clamp(1, 2)).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}

/// "Hamza Rafiq" -> "Hamza R."
String shortName(String name) {
  final w = name.split(RegExp(r'\s+')).where((s) => s.isNotEmpty).toList();
  return w.length < 2 ? name : '${w.first} ${w.last[0]}.';
}
