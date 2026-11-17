/// Card screenshots over the relay (`task_shot`): the loader and the
/// widget that fetches once and shows the PNG, a spinner or a broken glyph.
library;

import 'dart:convert';
import 'dart:typed_data';

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:todo_implementer/sync/board_relay.dart';

/// Loads a screenshot of the card as PNG bytes, or null.
typedef ShotLoad = Future<List<int>?> Function(String name);

/// One card screenshot, fetched over the relay (`task_shot`).
class ShotImage extends StatefulWidget {
  /// Creates the image.
  const new({required this.name, required this.load, super.key});

  /// Screenshot name.
  final String name;

  /// Loader.
  final ShotLoad load;

  @override
  State<ShotImage> createState() => _ShotImageState();
}

class _ShotImageState extends State<ShotImage> {
  late final Future<List<int>?> _bytes = widget.load(widget.name);

  @override
  Widget build(BuildContext context) => FutureBuilder<List<int>?>(
    future: _bytes,
    builder: (_, snap) {
      final bytes = snap.data;
      if (snap.connectionState != ConnectionState.done) {
        return const LinearProgressIndicator(semanticsLabel: 'shot');
      }
      if (bytes == null) {
        return const Icon(
          Icons.broken_image_outlined,
          color: AppPalette.danger,
        );
      }
      return Image.memory(
        Uint8List.fromList(bytes),
        key: ValueKey('shot-${widget.name}'),
        semanticLabel: widget.name,
      );
    },
  );
}

/// [relay]'s `task_shot` for [card] as a [ShotLoad].
ShotLoad shotLoader(BoardRelay relay, String card) => (name) async {
  final out = await relay.send('task_shot', {'card': card, 'name': name});
  if (out is! RelayOk) return null;
  final b64 = out.data['png_b64'];
  return b64 is String ? base64Decode(b64) : null;
};
