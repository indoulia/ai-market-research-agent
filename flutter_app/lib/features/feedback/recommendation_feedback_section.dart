import 'dart:math';

import 'package:flutter/material.dart';

import '../../design_system/design_system.dart';
import 'feedback.dart';
import 'feedback_repository.dart';

enum _SubmitState { idle, submitting, submitted, failed }

/// EPIC-M1.142 — "Recommendation Feedback": one-tap useful/not-useful,
/// an optional structured reason, and an optional comment. UX rules: at
/// most two interactions for the common case, no modal dialog, and an
/// explicit acknowledgement that feedback informs learning/analysis but
/// never changes the model instantly (M1.141's own rule).
class RecommendationFeedbackSection extends StatefulWidget {
  final int recommendationId;

  /// The active prediction's `modelVersion` string (e.g.
  /// `detail.predictionVersion['modelVersion']`) — EPIC-M1.141's real
  /// contract matches this exact string server-side, not the whole
  /// version bundle.
  final String predictionVersion;
  final FeedbackRepository? repository;

  const RecommendationFeedbackSection({
    super.key,
    required this.recommendationId,
    required this.predictionVersion,
    this.repository,
  });

  @override
  State<RecommendationFeedbackSection> createState() =>
      _RecommendationFeedbackSectionState();
}

class _RecommendationFeedbackSectionState
    extends State<RecommendationFeedbackSection> {
  late final FeedbackRepository _repository;
  _SubmitState _state = _SubmitState.idle;
  FeedbackType? _reason;
  String? _idempotencyKey;
  final TextEditingController _commentController = TextEditingController();
  final Random _random = Random();

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? FeedbackRepository();
  }

  @override
  void dispose() {
    _commentController.dispose();
    super.dispose();
  }

  Future<void> _submit(FeedbackType type) async {
    // A manual retry of the *same* reason reuses its idempotency key (so a
    // repeated tap after a failure doesn't create a duplicate feedback
    // row); picking a different reason is a genuinely new submission and
    // gets a fresh one.
    if (_reason != type) {
      _idempotencyKey =
          '${DateTime.now().microsecondsSinceEpoch}-${_random.nextInt(1 << 32)}';
    }
    setState(() {
      _reason = type;
      _state = _SubmitState.submitting;
    });
    try {
      await _repository.submit(
        recommendationId: widget.recommendationId,
        type: type,
        predictionVersion: widget.predictionVersion,
        comment: _commentController.text,
        idempotencyKey: _idempotencyKey,
      );
      if (!mounted) return;
      setState(() => _state = _SubmitState.submitted);
    } catch (_) {
      if (!mounted) return;
      setState(() => _state = _SubmitState.failed);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return MraCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Was this recommendation useful?',
            style: theme.textTheme.titleMedium,
          ),
          const SizedBox(height: MraSpacing.sm),
          if (_state == _SubmitState.submitted)
            _AcknowledgementText(learningNote: true)
          else ...[
            Row(
              children: [
                FilledButton.icon(
                  icon: const Icon(Icons.thumb_up_outlined),
                  label: const Text('Useful'),
                  onPressed: _state == _SubmitState.submitting
                      ? null
                      : () => _submit(FeedbackType.useful),
                ),
                const SizedBox(width: MraSpacing.sm),
                OutlinedButton.icon(
                  icon: const Icon(Icons.thumb_down_outlined),
                  label: const Text('Not useful'),
                  onPressed: _state == _SubmitState.submitting
                      ? null
                      : () => _submit(FeedbackType.notUseful),
                ),
              ],
            ),
            const SizedBox(height: MraSpacing.md),
            Wrap(
              spacing: MraSpacing.sm,
              runSpacing: MraSpacing.sm,
              children:
                  [
                    FeedbackType.targetRealistic,
                    FeedbackType.targetTooHigh,
                    FeedbackType.targetTooLow,
                  ].map((type) {
                    return MraChip(
                      label: type.label,
                      selected: _reason == type,
                      onTap: _state == _SubmitState.submitting
                          ? null
                          : () => _submit(type),
                    );
                  }).toList(),
            ),
            const SizedBox(height: MraSpacing.md),
            TextField(
              controller: _commentController,
              decoration: const InputDecoration(
                hintText: 'Optional comment',
                isDense: true,
              ),
              maxLines: 2,
            ),
            const SizedBox(height: MraSpacing.sm),
            const _AcknowledgementText(learningNote: false),
            if (_state == _SubmitState.failed) ...[
              const SizedBox(height: MraSpacing.sm),
              Text(
                'Feedback could not be submitted — try again.',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.error,
                ),
              ),
            ],
          ],
        ],
      ),
    );
  }
}

class _AcknowledgementText extends StatelessWidget {
  final bool learningNote;
  const _AcknowledgementText({required this.learningNote});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final text = learningNote
        ? 'Thanks — this is queued for learning/analysis and will not '
              'change this or any live recommendation immediately.'
        : 'Feedback informs learning and analysis; it never changes a '
              'model instantly.';
    return Text(
      text,
      style: theme.textTheme.bodySmall?.copyWith(
        color: theme.colorScheme.onSurfaceVariant,
      ),
    );
  }
}
