/// Lenient readers for the JSON the worker publishes.
///
/// The worker validates every snapshot against `contracts/*.schema.json`
/// before it seals it, so the app reads fields by name and falls back to a
/// neutral value instead of throwing on a field a newer server added or an
/// older one omitted.
library;

/// A decoded JSON object.
typedef Json = Map<String, dynamic>;

/// The object at [key], or null.
Json? objOr(Json j, String key) {
  final v = j[key];
  return v is Map<String, dynamic> ? v : null;
}

/// The string at [key], or [or].
String str(Json j, String key, [String or = '']) {
  final v = j[key];
  return v is String ? v : or;
}

/// The string at [key], or null.
String? strOr(Json j, String key) {
  final v = j[key];
  return v is String ? v : null;
}

/// The number at [key] as a double, or [or].
double numOf(Json j, String key, [double or = 0]) {
  final v = j[key];
  return v is num ? v.toDouble() : or;
}

/// The integer at [key], or null.
int? intOr(Json j, String key) {
  final v = j[key];
  return v is num ? v.toInt() : null;
}

/// The bool at [key], or [or].
bool flag(Json j, String key, {bool or = false}) {
  final v = j[key];
  return v is bool ? v : or;
}

/// The objects in the list at [key].
List<Json> objs(Json j, String key) {
  final v = j[key];
  return v is List ? v.whereType<Json>().toList() : const [];
}

/// The strings in the list at [key].
List<String> strs(Json j, String key) {
  final v = j[key];
  return v is List ? v.whereType<String>().toList() : const [];
}
