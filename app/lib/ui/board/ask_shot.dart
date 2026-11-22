/// The approve/reject screenshot ask widget.
library;

import 'package:design_system/design_system.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/model/detail.dart';
import 'package:todo_implementer/ui/board/asks_view.dart';
import 'package:todo_implementer/ui/board/shot_image.dart';

/// A widget that shows a screenshot ask with approve/reject actions.
///
/// Displays the shot image if available, and when open, shows approve and
/// reject buttons. When closed, shows the final state icon.
class AskShot extends StatelessWidget {
  /// Creates the shot ask widget.
  const new({
    required this.ask,
    required this.onSend,
    required this.load,
    super.key,
  });

  /// The ask item containing the screenshot data.
  final AskItem ask;

  /// Callback to send the approve/reject request.
  final AskSend onSend;

  /// Function to load the screenshot image.
  final ShotLoad load;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      if (ask.shot case final shot?) ShotImage(name: shot, load: load),
      if (ask.open)
        Row(
          children: [
            IconButton(
              key: ValueKey('ask-approve-${ask.id}'),
              tooltip: 'approve',
              icon: const Icon(
                Icons.thumb_up_alt_outlined,
                semanticLabel: 'Approve',
              ),
              onPressed: () => onSend('ask_approve', {'ask': ask.id}),
            ),
            IconButton(
              key: ValueKey('ask-reject-${ask.id}'),
              tooltip: 'reject',
              icon: const Icon(
                Icons.thumb_down_alt_outlined,
                semanticLabel: 'Reject',
              ),
              onPressed: () => onSend('ask_reject', {'ask': ask.id}),
            ),
          ],
        )
      else
        Icon(
          ask.state == 'approved' ? Icons.thumb_up_alt : Icons.thumb_down_alt,
          color: ask.state == 'approved'
              ? AppPalette.success
              : AppPalette.danger,
        ),
    ],
  );
}
