/// The web build's draft images: in its preferences (it has no files).
library;

import 'package:todo_implementer/ui/board/draft_images_base.dart';

export 'package:todo_implementer/ui/board/draft_images_base.dart';

/// The store this platform uses.
DraftImages platformDraftImages() => PrefsDraftImages();
