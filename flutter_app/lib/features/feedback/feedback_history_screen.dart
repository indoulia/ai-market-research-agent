import 'package:flutter/material.dart';

import '../../core/api_exception.dart';
import '../../design_system/design_system.dart';
import 'feedback.dart';
import 'feedback_history_item.dart';
import 'feedback_repository.dart';

enum _LoadState { loading, error, loaded }

/// EPIC-M3.10 — "Feedback history": every feedback event the signed-in
/// user has submitted, newest first, plus the same "queued for learning,
/// never an immediate model change" disclosure the submission flow
/// (`RecommendationFeedbackSection`, EPIC-M1.142) already shows — repeated
/// here since a user reviewing past feedback is exactly the moment that
/// disclosure matters again.
class FeedbackHistoryScreen extends StatefulWidget {
  final FeedbackRepository? repository;

  const FeedbackHistoryScreen({super.key, this.repository});

  @override
  State<FeedbackHistoryScreen> createState() => _FeedbackHistoryScreenState();
}

class _FeedbackHistoryScreenState extends State<FeedbackHistoryScreen> {
  late final FeedbackRepository _repository;
  _LoadState _state = _LoadState.loading;
  List<FeedbackHistoryItem> _items = const [];
  String? _cursor;
  bool _loadingMore = false;
  ApiException? _error;

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? FeedbackRepository();
    _load();
  }

  Future<void> _load() async {
    setState(() => _state = _LoadState.loading);
    try {
      final page = await _repository.fetchHistory();
      setState(() {
        _items = page.items;
        _cursor = page.nextCursor;
        _state = _LoadState.loaded;
      });
    } catch (e) {
      setState(() {
        _error = e is ApiException ? e : ApiException.network(e);
        _state = _LoadState.error;
      });
    }
  }

  Future<void> _loadMore() async {
    if (_cursor == null || _loadingMore) return;
    setState(() => _loadingMore = true);
    try {
      final page = await _repository.fetchHistory(cursor: _cursor);
      setState(() {
        _items = [..._items, ...page.items];
        _cursor = page.nextCursor;
        _loadingMore = false;
      });
    } catch (_) {
      setState(() => _loadingMore = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return SingleChildScrollView(
      padding: const EdgeInsets.all(MraSpacing.lg),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 700),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Feedback history', style: theme.textTheme.headlineSmall),
            const SizedBox(height: MraSpacing.sm),
            Text(
              'Feedback you submit is queued for learning and analysis; it '
              'never changes a recommendation or model instantly.',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: MraSpacing.xl),
            _buildBody(context),
          ],
        ),
      ),
    );
  }

  Widget _buildBody(BuildContext context) {
    switch (_state) {
      case _LoadState.loading:
        return const MraCard(child: SkeletonCard());
      case _LoadState.error:
        return MraStateView.error(message: _error?.message, onAction: _load);
      case _LoadState.loaded:
        if (_items.isEmpty) {
          return const MraStateView.empty(
            message: "You haven't submitted any feedback yet.",
          );
        }
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            for (var i = 0; i < _items.length; i++)
              TimelineEventRow(
                title: _titleFor(_items[i]),
                subtitle: _subtitleFor(_items[i]),
                timestampLabel: _formatDate(_items[i].createdAt),
                tone: _toneFor(_items[i]),
                isLast: i == _items.length - 1 && _cursor == null,
              ),
            if (_cursor != null)
              Padding(
                padding: const EdgeInsets.only(top: MraSpacing.sm),
                child: OutlinedButton(
                  onPressed: _loadingMore ? null : _loadMore,
                  child: Text(_loadingMore ? 'Loading…' : 'Load more'),
                ),
              ),
          ],
        );
    }
  }

  String _titleFor(FeedbackHistoryItem item) =>
      'Recommendation #${item.recommendationId} — ${item.type.label}';

  String _subtitleFor(FeedbackHistoryItem item) {
    final impact = item.learningImpact == 'queued'
        ? 'Queued for learning'
        : 'Informational';
    final note = item.note;
    return note == null || note.isEmpty ? impact : '$impact · "$note"';
  }

  MraTimelineTone _toneFor(FeedbackHistoryItem item) => switch (item.type) {
    FeedbackType.useful ||
    FeedbackType.targetRealistic => MraTimelineTone.positive,
    FeedbackType.notUseful ||
    FeedbackType.targetTooHigh ||
    FeedbackType.targetTooLow => MraTimelineTone.warning,
    FeedbackType.reason => MraTimelineTone.neutral,
  };

  String _formatDate(DateTime date) {
    final local = date.toLocal();
    return '${local.year}-${local.month.toString().padLeft(2, '0')}-${local.day.toString().padLeft(2, '0')}';
  }
}
