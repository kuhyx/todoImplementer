/// The add-task box's text as `new_task` sends it: the first real line is
/// the title, the rest the body (`newtask/titles.py`, T2481).
library;

/// The schema's title cap.
const kMaxTitle = 200;

final _imageRef = RegExp(r'\[Image #\d+\]');

/// The line's text with its `[Image #N]` refs out, spaces folded.
String _cleanLine(String line) => _imageRef.hasMatch(line)
    ? line
          .replaceAll(_imageRef, ' ')
          .split(RegExp(r'\s+'))
          .where((w) => w.isNotEmpty)
          .join(' ')
    : line.trim();

/// (title, body), the server's `newtask/titles.py` rule (T2481): the first
/// line of real text with its image refs out, cut to [kMaxTitle]; a note with
/// no text keeps its first line. A skipped or cleaned ref line, or a cut,
/// keeps the whole text as the body, so no ref is lost.
(String, String) splitNote(String text) {
  final all = text.trim();
  final lines = all.split('\n');
  final found = lines.indexWhere((line) => _cleanLine(line).isNotEmpty);
  final at = found < 0 ? 0 : found;
  final title = found < 0 ? lines.first.trim() : _cleanLine(lines[at]);
  final lossy =
      found >= 0 &&
      (title != lines[at].trim() ||
          lines.take(at).any((line) => line.trim().isNotEmpty));
  if (title.length > kMaxTitle) {
    return (title.substring(0, kMaxTitle).trim(), all);
  }
  return (title, lossy ? all : lines.skip(at + 1).join('\n').trim());
}

/// True when [text] gives a title `new_task` accepts.
bool newTaskValid(String text) => splitNote(text).$1.isNotEmpty;
