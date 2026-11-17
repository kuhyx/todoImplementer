/// Answering a spec card's open questions: the questions come from
/// `task_detail` (Claude's content), each field starts on the recommended
/// answer, and the send button posts `task_spec_answers`.
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:todo_implementer/model/json.dart';

/// One open spec question.
class SpecQuestion {
  /// Creates the question.
  const new(this.id, this.title, this.body, this.recommendation);

  /// Parses `common.schema.json#/$defs/question`.
  factory fromJson(Json j) => SpecQuestion(
    str(j, 'id'),
    str(j, 'title'),
    str(j, 'body'),
    str(j, 'recommendation'),
  );

  /// `Q1`, `Q2`, ...
  final String id;

  /// Question title, body and recommended answer (Claude's content).
  final String title;

  /// Question body.
  final String body;

  /// Recommended answer, the field's start value.
  final String recommendation;
}

/// The unanswered questions of a `task_detail` result.
List<SpecQuestion> openQuestions(Json detail) => [
  for (final q in objs(detail, 'questions'))
    if (q['answer'] == null) SpecQuestion.fromJson(q),
];

/// Fields for [questions] and a send button.
class SpecAnswers extends StatefulWidget {
  /// Creates the form.
  const new({required this.questions, required this.onSend, super.key});

  /// The open questions.
  final List<SpecQuestion> questions;

  /// Sends `{answers: {Q1: ...}}`.
  final Future<void> Function(Map<String, String> answers) onSend;

  @override
  State<SpecAnswers> createState() => _SpecAnswersState();
}

class _SpecAnswersState extends State<SpecAnswers> {
  late final Map<String, TextEditingController> _fields = {
    for (final q in widget.questions)
      q.id: TextEditingController(text: q.recommendation),
  };
  bool _busy = false;

  @override
  void dispose() {
    for (final c in _fields.values) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _send() async {
    setState(() => _busy = true);
    final answers = {
      for (final e in _fields.entries)
        if (e.value.text.trim().isNotEmpty) e.key: e.value.text.trim(),
    };
    try {
      await widget.onSend(answers);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      for (final q in widget.questions) ...[
        Text(q.title, style: const TextStyle(fontWeight: FontWeight.bold)),
        if (q.body.isNotEmpty)
          Text(q.body, style: const TextStyle(color: AppPalette.mutedOnDark)),
        TextField(
          key: ValueKey('answer-${q.id}'),
          controller: _fields[q.id],
          minLines: 1,
          maxLines: 4,
        ),
        const SizedBox(height: AppSpacing.sm),
      ],
      Align(
        alignment: Alignment.centerRight,
        child: IconButton.filled(
          key: const Key('answers-send'),
          onPressed: _busy ? null : _send,
          icon: _busy
              ? const SizedBox.square(
                  dimension: AppSpacing.md,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(Icons.send, semanticLabel: 'Send answers'),
        ),
      ),
    ],
  );
}
