/// Number and time formatting shared by every usage view, the same rules as
/// `web/src/usage/format.ts`. The em dash stands for "no value".
library;

/// Shown where a cell has no value.
const dash = '—';

const _minute = 60;
const _hour = 3600;
const _units = <(double, String)>[(1e9, 'B'), (1e6, 'M'), (1e3, 'k')];

/// `$1.23`, or `$123` from 100 up.
String usd(num? value) {
  if (value == null) return dash;
  return value >= 100
      ? '\$${value.toStringAsFixed(0)}'
      : '\$${value.toStringAsFixed(2)}';
}

/// A 0..1 share as `12.3%`.
String share(num? value) =>
    value == null ? dash : '${(value * 100).toStringAsFixed(1)}%';

/// 12 345 -> `12.3k`; small numbers stay whole.
String compact(num? value) {
  if (value == null) return dash;
  for (final (size, unit) in _units) {
    if (value.abs() >= size) {
      return '${(value / size).toStringAsFixed(1)}$unit';
    }
  }
  return '${value.round()}';
}

/// Seconds as `42s`, `17m` or `3h 05m`.
String duration(num? seconds) {
  if (seconds == null) return dash;
  if (seconds < _minute) return '${seconds.round()}s';
  final minutes = (seconds / _minute).round();
  if (seconds < _hour) return '${minutes}m';
  final rest = '${minutes % _minute}'.padLeft(2, '0');
  return '${minutes ~/ _minute}h ${rest}m';
}

/// Epoch seconds as `2026-11-05 13:15`, local time.
String stamp(num? epoch) {
  if (epoch == null) return dash;
  final d = DateTime.fromMillisecondsSinceEpoch((epoch * 1000).round());
  String two(int n) => '$n'.padLeft(2, '0');
  return '${d.year}-${two(d.month)}-${two(d.day)} '
      '${two(d.hour)}:${two(d.minute)}';
}

/// A whole number as is, anything else with two decimals.
String plain(num? value) {
  if (value == null) return dash;
  return value == value.roundToDouble() && value.abs() < 1e15
      ? '${value.round()}'
      : value.toStringAsFixed(2);
}

/// Any cell as display text; objects print as JSON-ish, never `Instance`.
String cellText(Object? value) => switch (value) {
  null || '' => dash,
  final num n => plain(n),
  final String s => s,
  // Booleans read as a mark, not a word (textgate).
  final bool b => b ? '✓' : '✗',
  _ => '$value',
};

/// The month-day part of an ISO day (`2026-11-05` -> `11-05`).
String dayLabel(String day) => day.length >= 10 ? day.substring(5) : day;
