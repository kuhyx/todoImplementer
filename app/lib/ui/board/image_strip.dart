/// The image row under a text box: gallery and camera buttons, the reason
/// glyph of a refused image, and one #N chip per image with its thumbnail
/// and a remove button (textgate: glyphs, the numbers kuhy asked for, and
/// reasons only as screen-reader text). Pastes come in through the box's
/// own `contentInsertionConfiguration` ([ImageAttach.paste]).
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/ui/board/image_attach.dart';

/// Where a picked image comes from.
enum PickFrom {
  /// The system photo picker.
  gallery,

  /// The camera app.
  camera,
}

/// Picks up to [room] images from [from]; empty when kuhy cancels.
typedef PickImages = Future<List<Uint8List>> Function(PickFrom from, int room);

// Long side and JPEG quality the platform re-encodes to: a phone photo
// lands near 0.5 MB, so eight fit the relay's total budget.
const double _side = 1600;
const int _quality = 80;

/// The platform picker (image_picker): downscaled and re-encoded on the
/// phone; read as bytes so the web build works too.
Future<List<Uint8List>> pickImages(PickFrom from, int room) async {
  final picker = ImagePicker();
  final files = from == PickFrom.camera || room < 2
      ? [
          ?await picker.pickImage(
            source: from == PickFrom.camera
                ? ImageSource.camera
                : ImageSource.gallery,
            maxWidth: _side,
            maxHeight: _side,
            imageQuality: _quality,
          ),
        ]
      : await picker.pickMultiImage(
          maxWidth: _side,
          maxHeight: _side,
          imageQuality: _quality,
          limit: room,
        );
  return [for (final f in files) await f.readAsBytes()];
}

/// The picker every strip uses; tests swap it.
PickImages imagePicker = pickImages;

/// Glyph and screen-reader reason of a refusal.
(IconData, String) problemGlyph(ImageProblem p) => switch (p) {
  ImageProblem.type => (
    Icons.broken_image_outlined,
    'Not a PNG, JPEG, WebP or GIF image',
  ),
  ImageProblem.size => (
    Icons.photo_size_select_large,
    'Too large for this message, even shrunk',
  ),
  ImageProblem.count => (Icons.filter_9_plus, 'At most $kMaxImages images'),
  ImageProblem.unavailable => (
    Icons.no_photography_outlined,
    'The picker or camera gave no image',
  ),
};

/// The row for [attach]; keys start with [prefix]. With a [field] the
/// buttons share one row with it (and [trailing], the send arrow) and the
/// chips go in a strip above, so no control sits below the fold.
class ImageStrip extends StatefulWidget {
  /// Creates the row.
  const new({
    required this.attach,
    required this.prefix,
    this.field,
    this.trailing,
    super.key,
  });

  /// The text field to put between the buttons and [trailing].
  final Widget? field;

  /// What ends the row (the send arrow): after the field, or after the
  /// chips when there is no field (the add-task page, T2352).
  final Widget? trailing;

  /// The box's images.
  final ImageAttach attach;

  /// Key prefix (`detail`, `sheet`, `nt`).
  final String prefix;

  @override
  State<ImageStrip> createState() => _ImageStripState();
}

class _ImageStripState extends State<ImageStrip> {
  bool _busy = false;

  Future<void> _pick(PickFrom from) async {
    final attach = widget.attach;
    setState(() => _busy = true);
    try {
      final room = kMaxImages - attach.images.length;
      for (final bytes in await imagePicker(from, room)) {
        await attach.add(bytes);
      }
    } on PlatformException {
      attach.refuse(ImageProblem.unavailable);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Widget _button(PickFrom from, IconData icon, String spoken) => IconButton(
    key: Key('${widget.prefix}-${from.name}'),
    icon: Icon(icon, semanticLabel: spoken),
    onPressed: _busy || widget.attach.images.length >= kMaxImages
        ? null
        : () => _pick(from),
  );

  // A chip drawn by hand: InputChip asserts when its avatar is taller than
  // its label, and the thumbnail is the point of the chip.
  Widget _chip(int i, Uint8List bytes) => Container(
    key: ValueKey('${widget.prefix}-image-${i + 1}'),
    margin: const EdgeInsets.only(right: AppSpacing.xs),
    padding: const EdgeInsets.only(left: AppSpacing.xs),
    decoration: BoxDecoration(
      border: Border.all(color: Theme.of(context).colorScheme.outline),
      borderRadius: BorderRadius.circular(AppSpacing.sm),
    ),
    child: Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        ClipRRect(
          borderRadius: BorderRadius.circular(AppSpacing.xs),
          child: Image.memory(
            bytes,
            width: AppSpacing.xl,
            height: AppSpacing.xl,
            fit: BoxFit.cover,
            gaplessPlayback: true,
          ),
        ),
        const SizedBox(width: AppSpacing.xs),
        Text('#${i + 1}'),
        IconButton(
          visualDensity: VisualDensity.compact,
          icon: Icon(Icons.close, semanticLabel: 'Remove image #${i + 1}'),
          onPressed: () => widget.attach.remove(i),
        ),
      ],
    ),
  );

  Widget _state() {
    final problem = widget.attach.problem;
    if (_busy || widget.attach.busy) {
      return SizedBox.square(
        key: Key('${widget.prefix}-image-busy'),
        dimension: AppSpacing.md,
        child: const CircularProgressIndicator(
          strokeWidth: 2,
          semanticsLabel: 'Adding images',
        ),
      );
    }
    if (problem == null) return const SizedBox.shrink();
    return Icon(
      problemGlyph(problem).$1,
      key: Key('${widget.prefix}-image-problem'),
      color: AppPalette.danger,
      semanticLabel: problemGlyph(problem).$2,
    );
  }

  Widget _chips(List<Uint8List> images) => SingleChildScrollView(
    scrollDirection: Axis.horizontal,
    child: Row(children: [for (final (i, b) in images.indexed) _chip(i, b)]),
  );

  List<Widget> _buttons() => [
    _button(PickFrom.gallery, Icons.photo_library_outlined, 'Gallery'),
    _button(PickFrom.camera, Icons.photo_camera_outlined, 'Camera'),
    _state(),
  ];

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: widget.attach,
    builder: (context, _) {
      final images = widget.attach.images;
      final field = widget.field;
      if (field == null) {
        return Row(
          children: [
            ..._buttons(),
            Expanded(child: _chips(images)),
            ?widget.trailing,
          ],
        );
      }
      return Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (images.isNotEmpty) _chips(images),
          Row(
            children: [
              ..._buttons(),
              Expanded(child: field),
              ?widget.trailing,
            ],
          ),
        ],
      );
    },
  );
}
