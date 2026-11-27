/// A note's images (T2535): thumbnails fetched over the relay (`image_get`)
/// from the PC's todo-images folder; a tap opens one full size, pinch to zoom.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:design_system/design_system.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/model/board.dart';
import 'package:todo_implementer/sync/board_relay.dart';

/// Thumbnail edge in logical pixels.
const double kThumb = 72;

/// Loaded images kept for the sheet and the detail page; a dufs image never
/// changes under its name, so a hit needs no refetch. Small: the oldest go.
const int kImageCacheSize = 24;

final Map<String, Future<Uint8List?>> _cache = {};

/// [relay]'s `image_get` for [image], cached; a failure is not cached.
Future<Uint8List?> loadNoteImage(BoardRelay relay, NoteImage image) {
  final hit = _cache[image.path];
  if (hit != null) return hit;
  if (_cache.length >= kImageCacheSize) {
    unawaited(_cache.remove(_cache.keys.first));
  }
  final load = _fetch(relay, image);
  _cache[image.path] = load;
  unawaited(load.then((bytes) => bytes ?? _cache.remove(image.path)));
  return load;
}

/// Forgets every loaded image (tests).
void clearNoteImages() => _cache.clear();

Future<Uint8List?> _fetch(BoardRelay relay, NoteImage image) async {
  final out = await relay.send('image_get', {
    'folder': image.folder,
    'file': image.file,
  });
  if (out is! RelayOk) return null;
  final b64 = out.data['data_b64'] ?? out.data['png_b64'];
  return b64 is String ? base64Decode(b64) : null;
}

/// The row of [images] as thumbnails; nothing when there are none.
class NoteImages extends StatelessWidget {
  /// Creates the row.
  const new({required this.images, required this.relay, super.key});

  /// The note's images.
  final List<NoteImage> images;

  /// Where `image_get` goes.
  final BoardRelay relay;

  @override
  Widget build(BuildContext context) {
    if (images.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
      child: Wrap(
        spacing: AppSpacing.sm,
        runSpacing: AppSpacing.sm,
        children: [for (final i in images) NoteThumb(image: i, relay: relay)],
      ),
    );
  }
}

/// One note image as a square thumbnail; [zoom] makes a tap open it full
/// screen (off on the board tile, whose own tap opens the card sheet).
class NoteThumb extends StatefulWidget {
  /// Creates the thumbnail.
  const new({
    required this.image,
    required this.relay,
    this.size = kThumb,
    this.zoom = true,
    super.key,
  });

  /// The image.
  final NoteImage image;

  /// Where `image_get` goes.
  final BoardRelay relay;

  /// Edge in logical pixels.
  final double size;

  /// Whether a tap opens it full screen.
  final bool zoom;

  @override
  State<NoteThumb> createState() => _ThumbState();
}

class _ThumbState extends State<NoteThumb> {
  late final Future<Uint8List?> _bytes = loadNoteImage(
    widget.relay,
    widget.image,
  );

  Future<void> _open(Uint8List bytes) => showDialog<void>(
    context: context,
    builder: (ctx) => Dialog.fullscreen(
      backgroundColor: AppPalette.ink,
      child: GestureDetector(
        onTap: () => Navigator.of(ctx).pop(),
        child: InteractiveViewer(
          maxScale: 8,
          child: Center(
            child: Image.memory(bytes, semanticLabel: widget.image.file),
          ),
        ),
      ),
    ),
  );

  @override
  Widget build(BuildContext context) => SizedBox.square(
    dimension: widget.size,
    child: FutureBuilder<Uint8List?>(
      future: _bytes,
      builder: (_, snap) {
        final bytes = snap.data;
        if (snap.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        if (bytes == null) {
          return const Icon(
            Icons.broken_image_outlined,
            color: AppPalette.danger,
          );
        }
        final thumb = ClipRRect(
          borderRadius: BorderRadius.circular(AppRadius.sm),
          child: Image.memory(
            bytes,
            fit: BoxFit.cover,
            cacheWidth: (widget.size * 3).round(),
            semanticLabel: widget.image.file,
          ),
        );
        if (!widget.zoom) {
          return KeyedSubtree(
            key: ValueKey('tile-image-${widget.image.path}'),
            child: thumb,
          );
        }
        return InkWell(
          key: ValueKey('note-image-${widget.image.path}'),
          onTap: () => _open(bytes),
          child: thumb,
        );
      },
    ),
  );
}
