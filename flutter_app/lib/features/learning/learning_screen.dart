import 'package:flutter/material.dart';

import '../../core/api_exception.dart';
import '../../design_system/design_system.dart';
import 'learning_experiment.dart';
import 'learning_history_entry.dart';
import 'learning_repository.dart';
import 'learning_summary.dart';

enum _LoadState { loading, error, loaded }

/// EPIC-M3.9 — "Learning & Self-Improvement": a read-only view of MRA's
/// controlled learning process (learning cycles, promotions/rejections,
/// champion/challenger comparisons, rollbacks, candidate experiments and
/// discovered failure patterns), consuming `GET /learning/{summary,
/// history,experiments}` only. No control on this screen can mutate
/// production model/learning state (AC: "UI never directly modifies
/// production models") -- every value shown here links back to the
/// already-computed evidence that produced it (methodology version,
/// evidence count, decision reason).
class LearningScreen extends StatefulWidget {
  final LearningRepository? repository;

  const LearningScreen({super.key, this.repository});

  @override
  State<LearningScreen> createState() => _LearningScreenState();
}

class _LearningScreenState extends State<LearningScreen> {
  late final LearningRepository _repository;

  _LoadState _state = _LoadState.loading;
  ApiException? _error;

  LearningSummary? _summary;
  List<LearningHistoryEntry> _history = const [];
  List<LearningExperiment> _experiments = const [];

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? LearningRepository();
    _load();
  }

  Future<void> _load() async {
    setState(() => _state = _LoadState.loading);
    try {
      final results = await Future.wait([
        _repository.fetchSummary(),
        _repository.fetchHistory(),
        _repository.fetchExperiments(),
      ]);
      setState(() {
        _summary = results[0] as LearningSummary;
        _history = results[1] as List<LearningHistoryEntry>;
        _experiments = results[2] as List<LearningExperiment>;
        _state = _LoadState.loaded;
      });
    } catch (e) {
      setState(() {
        _error = e is ApiException ? e : ApiException.network(e);
        _state = _LoadState.error;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    switch (_state) {
      case _LoadState.loading:
        return const Padding(
          padding: EdgeInsets.all(MraSpacing.lg),
          child: MraCard(child: SkeletonCard()),
        );
      case _LoadState.error:
        return MraStateView.error(message: _error?.message, onAction: _load);
      case _LoadState.loaded:
        return _buildLoaded(context);
    }
  }

  Widget _buildLoaded(BuildContext context) {
    final theme = Theme.of(context);
    final summary = _summary!;
    return RefreshIndicator(
      onRefresh: _load,
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(MraSpacing.lg),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 1200),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      'Learning & Self-Improvement',
                      style: theme.textTheme.headlineSmall,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  IconButton(
                    tooltip: 'Refresh',
                    icon: const Icon(Icons.refresh),
                    onPressed: _load,
                  ),
                ],
              ),
              const SizedBox(height: MraSpacing.xs),
              Text(
                'How Marksy learns from real outcomes -- read-only. Nothing on '
                'this screen changes production model behavior.',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
              const SizedBox(height: MraSpacing.lg),
              _buildKpiGrid(summary),
              const SizedBox(height: MraSpacing.xl),
              if (summary.championChallenger != null) ...[
                _buildChampionChallengerCard(
                  context,
                  summary.championChallenger!,
                ),
                const SizedBox(height: MraSpacing.xl),
              ],
              Text(
                'Failure patterns discovered',
                style: theme.textTheme.titleMedium,
              ),
              const SizedBox(height: MraSpacing.sm),
              _buildSignalsSection(context, summary.recentSignals),
              const SizedBox(height: MraSpacing.xl),
              Text('Candidate experiments', style: theme.textTheme.titleMedium),
              const SizedBox(height: MraSpacing.sm),
              _buildExperimentsSection(context),
              const SizedBox(height: MraSpacing.xl),
              Text('Learning history', style: theme.textTheme.titleMedium),
              const SizedBox(height: MraSpacing.sm),
              _buildHistorySection(context),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildKpiGrid(LearningSummary s) {
    Widget card(String label, String value, {IconData? icon}) => SizedBox(
      width: 200,
      child: KpiStatCard(label: label, value: value, icon: icon),
    );

    return Wrap(
      spacing: MraSpacing.sm,
      runSpacing: MraSpacing.sm,
      children: [
        card(
          'Current model',
          s.currentModelVersion ?? 'None promoted yet',
          icon: Icons.smart_toy_outlined,
        ),
        card(
          'Promotions',
          '${s.promotionCounts.promoted} promoted / ${s.promotionCounts.rejected} rejected',
          icon: Icons.rule_outlined,
        ),
        card(
          'Rollbacks',
          s.rollbackCount.toString(),
          icon: Icons.undo_outlined,
        ),
        card(
          'Experiments',
          '${s.experimentCounts.ready} ready / ${s.experimentCounts.total} total',
          icon: Icons.science_outlined,
        ),
        card(
          'Failure patterns',
          s.failurePatternCount.toString(),
          icon: Icons.warning_amber_outlined,
        ),
      ],
    );
  }

  Widget _buildChampionChallengerCard(
    BuildContext context,
    ChampionChallengerStatus status,
  ) {
    final theme = Theme.of(context);
    final validated = status.verdict == 'VALIDATED';
    return MraCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  'Champion / challenger status',
                  style: theme.textTheme.titleMedium,
                ),
              ),
              MraChip(
                label: status.verdict,
                tone: validated ? MraChipTone.positive : MraChipTone.warning,
              ),
            ],
          ),
          const SizedBox(height: MraSpacing.sm),
          Text(
            'Challenger ${status.challengerModelVersion} vs. champion '
            '${status.championModelVersion} -- n=${status.sampleCount}',
            style: theme.textTheme.bodyMedium,
          ),
          const SizedBox(height: MraSpacing.xs),
          Text(
            'Champion success rate: ${_fmtPct(status.championSuccessRate)} · '
            'Challenger success rate: ${_fmtPct(status.challengerSuccessRate)}',
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
          const SizedBox(height: MraSpacing.xs),
          Text(
            'Evidence: ${status.comparisonRuleVersion}, computed ${status.computedAt}',
            style: theme.textTheme.labelSmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSignalsSection(
    BuildContext context,
    List<LearningSignalSummary> signals,
  ) {
    if (signals.isEmpty) {
      return const MraStateView.empty(
        message: 'No recurring feedback patterns found yet.',
      );
    }
    final theme = Theme.of(context);
    return Column(
      children: signals
          .map(
            (s) => Padding(
              padding: const EdgeInsets.only(bottom: MraSpacing.sm),
              child: MraCard(
                child: Row(
                  children: [
                    MraChip(
                      label: s.verdict,
                      tone: s.isWeak
                          ? MraChipTone.warning
                          : MraChipTone.neutral,
                    ),
                    const SizedBox(width: MraSpacing.sm),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            '${s.category} / ${s.reasonCode}',
                            style: theme.textTheme.labelLarge,
                          ),
                          Text(
                            'n=${s.evaluatedCount} evaluated · success rate '
                            '${_fmtPct(s.successRate)} · ${s.distinctUserCount} '
                            'distinct user(s)',
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: theme.colorScheme.onSurfaceVariant,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
          )
          .toList(),
    );
  }

  Widget _buildExperimentsSection(BuildContext context) {
    if (_experiments.isEmpty) {
      return const MraStateView.empty(
        message: 'No candidate experiments have been created yet.',
      );
    }
    return Column(
      children: _experiments
          .map(
            (experiment) => Padding(
              padding: const EdgeInsets.only(bottom: MraSpacing.sm),
              child: _ExperimentCard(experiment: experiment),
            ),
          )
          .toList(),
    );
  }

  Widget _buildHistorySection(BuildContext context) {
    if (_history.isEmpty) {
      return const MraStateView.empty(
        message: 'No learning-cycle history recorded yet.',
      );
    }
    return MraCard(
      child: Column(
        children: [
          for (var i = 0; i < _history.length; i++)
            TimelineEventRow(
              title: _history[i].impact,
              subtitle:
                  'Evidence: ${_history[i].methodologyVersion}'
                  '${_history[i].evidenceCount != null ? ' · n=${_history[i].evidenceCount}' : ''}',
              timestampLabel: _formatDate(_history[i].createdAt),
              tone: _toneFor(_history[i].type),
              isLast: i == _history.length - 1,
            ),
        ],
      ),
    );
  }

  static MraTimelineTone _toneFor(String type) => switch (type) {
    LearningHistoryEventType.promotion => MraTimelineTone.positive,
    LearningHistoryEventType.rejection => MraTimelineTone.warning,
    LearningHistoryEventType.rollback => MraTimelineTone.error,
    _ => MraTimelineTone.neutral,
  };

  static String _fmtPct(double? v) =>
      v == null ? '—' : '${(v * 100).toStringAsFixed(1)}%';

  static String _formatDate(DateTime d) =>
      '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
}

class _ExperimentCard extends StatelessWidget {
  final LearningExperiment experiment;

  const _ExperimentCard({required this.experiment});

  MraChipTone get _statusTone => switch (experiment.status) {
    LearningExperimentStatus.ready => MraChipTone.positive,
    LearningExperimentStatus.insufficientSample => MraChipTone.warning,
    _ => MraChipTone.neutral,
  };

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return MraExpandableSection(
      title: experiment.name,
      initiallyExpanded: false,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              MraChip(label: experiment.status, tone: _statusTone),
              if (experiment.feedbackDriven) ...[
                const SizedBox(width: MraSpacing.xs),
                MraChip(label: 'Feedback-driven', tone: MraChipTone.info),
              ],
            ],
          ),
          const SizedBox(height: MraSpacing.sm),
          Text(experiment.hypothesis, style: theme.textTheme.bodyMedium),
          const SizedBox(height: MraSpacing.sm),
          ...experiment.arms.map(
            (arm) => Padding(
              padding: const EdgeInsets.only(bottom: MraSpacing.xs),
              child: Text(
                '${arm.armName} (${arm.modelVersion}, ${arm.windowLabel}): '
                '${arm.verdict ?? 'no result yet'}'
                '${arm.accuracy != null ? ' · accuracy ${(arm.accuracy! * 100).toStringAsFixed(1)}%' : ''}'
                '${arm.sampleCount != null ? ' · n=${arm.sampleCount}' : ''}',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                  fontWeight: arm.armName == experiment.bestArmName
                      ? FontWeight.w700
                      : null,
                ),
              ),
            ),
          ),
          const SizedBox(height: MraSpacing.xs),
          Text(
            'Evidence: ${experiment.methodologyVersion}',
            style: theme.textTheme.labelSmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
        ],
      ),
    );
  }
}
