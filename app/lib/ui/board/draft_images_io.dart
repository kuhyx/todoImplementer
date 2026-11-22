/// The phone's and the PC's draft images: one file each in the app's
/// support directory, `<N>.img` for `[Image #N+1]`.
library;

import 'dart:io';
import 'dart:typed_data';

import 'package:path_provider/path_provider.dart';
import 'package:todo_implementer/ui/board/draft_images_base.dart';

export 'package:todo_implementer/ui/board/draft_images_base.dart';

/// The store this platform uses.
DraftImages platformDraftImages() => FileDraftImages();

/// The images as files in one directory.
class FileDraftImages implements DraftImages {
  /// The store; [root] gives the parent directory (tests pass a temp one).
  new({Future<Directory> Function()? root})
    : _root = root ?? getApplicationSupportDirectory;

  final Future<Directory> Function() _root;

  Future<Directory> _dir() async =>
      Directory('${(await _root()).path}/newtask-draft');

  static int? _index(FileSystemEntity f) =>
      int.tryParse(f.uri.pathSegments.last.split('.img').first);

  @override
  Future<List<Uint8List>> load() async {
    try {
      final files = [
        for (final f in (await _dir()).listSync())
          if (f is File && f.path.endsWith('.img') && _index(f) != null) f,
      ]..sort((a, b) => _index(a)!.compareTo(_index(b)!));
      return [for (final f in files) await f.readAsBytes()];
    } on Object {
      return const [];
    }
  }

  @override
  Future<void> save(List<Uint8List> images) async {
    try {
      final dir = await _dir();
      await dir.create(recursive: true);
      for (var i = 0; i < images.length; i++) {
        // Written beside, then renamed: a kill mid-write leaves the old file.
        final part = File('${dir.path}/$i.part');
        await part.writeAsBytes(images[i], flush: true);
        await part.rename('${dir.path}/$i.img');
      }
      for (final f in dir.listSync()) {
        final at = _index(f);
        if (at == null || at >= images.length) await f.delete();
      }
    } on Object {
      // No support directory or a full disk: the images live in the page.
    }
  }
}
