/// Where the add-task draft keeps its images (T2493). Files on the phone and
/// the PC, so a keystroke's text save never rewrites them (Android keeps every
/// preferences key in one XML file, rewritten whole on each write); the web
/// build has no files and keeps them in its preferences (localStorage).
library;

export 'draft_images_io.dart'
    if (dart.library.js_interop) 'draft_images_web.dart';
