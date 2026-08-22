import 'dart:async';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../core/api_exception.dart';
import '../../design_system/design_system.dart';
import 'active_prediction.dart';
import 'active_prediction_card.dart';
import 'closed_predictions_table.dart';
import 'tracked_prediction.dart';
import 'tracking_breakdown.dart';
import 'tracking_filters.dart';
import 'tracking_filters_sheet.dart';
import 'tracking_repository.dart';
import 'tracking_summary.dart';
import 'tracking_timeseries.dart';
import 'tracking_trend_card.dart';

enum _LoadState { loading, error, loaded }

const _ranges = ['7d', '30d', '90d', '1y'];
const _secondaryMetrics = ['hitRate', 'return', 'calibration'];
const _dimensions = [
  'horizon',
  'sector',
  'marketCap',
  'regime',
  'setup',
  'stock',
];

/// EPIC-M3.8 — user-selectable auto-refresh cadence for the "Active
/// positions" monitoring section. `off` is the default: a live-monitoring
/// feed opts a user IN to polling rather than surprising them with
/// background network activity (AC: "user-selectable refresh behavior").
const _refreshIntervals = <String, Duration?>{
  'Off': null,
  '30s': Duration(seconds: 30),
  '1m': Duration(minutes: 1),
  '5m': Duration(minutes: 5),
};

/// EPIC-M1.148 — the "Tracking" destination: a historical view of MRA
/// performance, prediction outcomes and Trust Score evolution, consuming
/// EPIC-M1.147's real, merged `/tracking/*` contracts only — no client-side
/// recomputation of any rate/average the API already returns (AC: "no
/// dashboard widget duplicates calculations already returned by the API").
class TrackingScreen extends StatefulWidget {
  final TrackingRepository? repository;

  const TrackingScreen({super.key, this.repository});

  @override
  State<TrackingScreen> createState() => _TrackingScreenState();
}

class _TrackingScreenState extends State<TrackingScreen> {
  late final TrackingRepository _repository;

  _LoadState _state = _LoadState.loading;
  ApiException? _error;

  String _range = '30d';
  String _secondaryMetric = 'hitRate';
  String _dimension = 'horizon';
  TrackingFilters _filters = const TrackingFilters();
  final _sectorController = TextEditingController();
  final _symbolController = TextEditingController();

  TrackingSummary? _summary;
  TrackingTimeseries? _trustSeries;
  TrackingTimeseries? _secondarySeries;
  TrackingBreakdown? _breakdown;
  List<TrackedPrediction> _predictions = const [];
  String? _predictionsCursor;

  List<ActivePrediction> _activePredictions = const [];
  String? _activeCursor;
  bool _activeLoading = true;
  ApiException? _activeError;
  String _refreshLabel = 'Off';
  Timer? _refreshTimer;
  Timer? _filterDebounce;
  DateTime? _activeFetchedAt;

  bool _secondaryLoading = false;
  bool _breakdownLoading = false;
  bool _loadingMorePredictions = false;
  bool _loadingMoreActive = false;

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? TrackingRepository();
    _load();
    _loadActive();
  }

  @override
  void dispose() {
    _refreshTimer?.cancel();
    _filterDebounce?.cancel();
    _sectorController.dispose();
    _symbolController.dispose();
    super.dispose();
  }

  Future<void> _loadActive() async {
    setState(() {
      _activeLoading = true;
      _activeError = null;
    });
    try {
      final page = await _repository.fetchActivePredictions();
      setState(() {
        _activePredictions = page.items;
        _activeCursor = page.nextCursor;
        _activeFetchedAt = DateTime.now();
        _activeLoading = false;
      });
    } catch (e) {
      setState(() {
        _activeError = e is ApiException ? e : ApiException.network(e);
        _activeLoading = false;
      });
    }
  }

  Future<void> _loadMoreActive() async {
    if (_activeCursor == null || _loadingMoreActive) return;
    setState(() => _loadingMoreActive = true);
    try {
      final page = await _repository.fetchActivePredictions(
        cursor: _activeCursor,
      );
      setState(() {
        _activePredictions = [..._activePredictions, ...page.items];
        _activeCursor = page.nextCursor;
        _loadingMoreActive = false;
      });
    } catch (_) {
      setState(() => _loadingMoreActive = false);
    }
  }

  void _onRefreshLabelChanged(String label) {
    if (label == _refreshLabel) return;
    setState(() => _refreshLabel = label);
    _refreshTimer?.cancel();
    final interval = _refreshIntervals[label];
    if (interval != null) {
      _refreshTimer = Timer.periodic(interval, (_) => _loadActive());
    }
  }

  Future<void> _openActivePredictionDetail(ActivePrediction item) async {
    await showMraBottomSheet<void>(
      context: context,
      title: item.symbol,
      builder: (context) => _ActivePredictionDetailSheet(
        repository: _repository,
        predictionId: item.predictionId,
        fallback: item,
      ),
    );
  }

  // 90d/1y in day buckets would be dozens of noisy points on a compact
  // sparkline; week buckets keep the trend readable at those ranges.
  String get _bucket => (_range == '90d' || _range == '1y') ? 'week' : 'day';

  Future<void> _load() async {
    setState(() => _state = _LoadState.loading);
    try {
      final results = await Future.wait([
        _repository.fetchSummary(range: _range, filters: _filters),
        _repository.fetchTimeseries(
          metric: 'trust',
          range: _range,
          bucket: _bucket,
          filters: _filters,
        ),
        _repository.fetchTimeseries(
          metric: _secondaryMetric,
          range: _range,
          bucket: _bucket,
          filters: _filters,
        ),
        _repository.fetchBreakdown(dimension: _dimension, filters: _filters),
        _repository.fetchPredictions(status: 'closed', filters: _filters),
      ]);
      final page = results[4] as TrackedPredictionsPage;
      setState(() {
        _summary = results[0] as TrackingSummary;
        _trustSeries = results[1] as TrackingTimeseries;
        _secondarySeries = results[2] as TrackingTimeseries;
        _breakdown = results[3] as TrackingBreakdown;
        _predictions = page.items;
        _predictionsCursor = page.nextCursor;
        _state = _LoadState.loaded;
      });
    } catch (e) {
      setState(() {
        _error = e is ApiException ? e : ApiException.network(e);
        _state = _LoadState.error;
      });
    }
  }

  void _onRangeChanged(String range) {
    if (range == _range && _filters.from == null) return;
    setState(() {
      _range = range;
      // A quick-range chip always means "not a custom date range" -- clear
      // any from/to a prior "Custom range" picker call left set.
      if (_filters.from != null || _filters.to != null) {
        _filters = _filters.copyWith(clearRange: true);
      }
    });
    _load();
  }

  Future<void> _pickCustomDateRange() async {
    final now = DateTime.now();
    final picked = await showDateRangePicker(
      context: context,
      firstDate: DateTime(now.year - 5),
      lastDate: now,
      initialDateRange: (_filters.from != null && _filters.to != null)
          ? DateTimeRange(start: _filters.from!, end: _filters.to!)
          : null,
    );
    if (picked == null) return;
    setState(() {
      _filters = _filters.copyWith(from: picked.start, to: picked.end);
    });
    _load();
  }

  void _onFiltersChanged() {
    _load();
  }

  void _debouncedFiltersChanged() {
    _filterDebounce?.cancel();
    _filterDebounce = Timer(
      const Duration(milliseconds: 350),
      _onFiltersChanged,
    );
  }

  Future<void> _onSecondaryMetricChanged(String metric) async {
    if (metric == _secondaryMetric) return;
    setState(() {
      _secondaryMetric = metric;
      _secondaryLoading = true;
    });
    try {
      final series = await _repository.fetchTimeseries(
        metric: metric,
        range: _range,
        bucket: _bucket,
        filters: _filters,
      );
      setState(() {
        _secondarySeries = series;
        _secondaryLoading = false;
      });
    } catch (_) {
      // Keep the prior series visible rather than a full-screen error for a
      // secondary-section refresh; the user can retry via the chip again.
      setState(() => _secondaryLoading = false);
    }
  }

  Future<void> _onDimensionChanged(String dimension) async {
    if (dimension == _dimension) return;
    setState(() {
      _dimension = dimension;
      _breakdownLoading = true;
    });
    try {
      final breakdown = await _repository.fetchBreakdown(
        dimension: dimension,
        filters: _filters,
      );
      setState(() {
        _breakdown = breakdown;
        _breakdownLoading = false;
      });
    } catch (_) {
      setState(() => _breakdownLoading = false);
    }
  }

  Future<void> _loadMorePredictions() async {
    if (_predictionsCursor == null || _loadingMorePredictions) return;
    setState(() => _loadingMorePredictions = true);
    try {
      final page = await _repository.fetchPredictions(
        status: 'closed',
        cursor: _predictionsCursor,
        filters: _filters,
      );
      setState(() {
        _predictions = [..._predictions, ...page.items];
        _predictionsCursor = page.nextCursor;
        _loadingMorePredictions = false;
      });
    } catch (_) {
      setState(() => _loadingMorePredictions = false);
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
                      'Tracking',
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
              const SizedBox(height: MraSpacing.sm),
              _buildRangeSelector(),
              const SizedBox(height: MraSpacing.sm),
              _buildFiltersRow(context),
              const SizedBox(height: MraSpacing.lg),
              if (summary.smallSample) ...[
                MraChip(
                  label: 'Small sample this period — rates may be volatile',
                  tone: MraChipTone.warning,
                  icon: Icons.warning_amber_outlined,
                ),
                const SizedBox(height: MraSpacing.md),
              ],
              _buildKpiGrid(summary),
              const SizedBox(height: MraSpacing.xs),
              Text(
                summary.modelVersion == null
                    ? 'No model version evaluated in this window'
                    : 'Model: ${summary.modelVersion}',
                style: theme.textTheme.labelSmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
              const SizedBox(height: MraSpacing.xl),
              _buildActiveSection(context),
              const SizedBox(height: MraSpacing.xl),
              TrackingTrendCard(
                chartKey: const Key('trustTrendChart'),
                title: 'Trust Score trend',
                tooltip:
                    'Average latest Trust Score across genuine predictions '
                    'evaluated in each period. Trust combines calibration, '
                    'historical accuracy, and evidence quality.',
                series: _trustSeries!,
                formatValue: _fmtPctValue,
              ),
              const SizedBox(height: MraSpacing.sm),
              Align(
                alignment: Alignment.centerLeft,
                child: OutlinedButton.icon(
                  onPressed: () => context.push('/tracking/learning'),
                  icon: const Icon(Icons.school_outlined),
                  label: const Text('View learning insights'),
                ),
              ),
              const SizedBox(height: MraSpacing.lg),
              _buildSecondaryMetricSelector(),
              const SizedBox(height: MraSpacing.sm),
              _secondaryLoading
                  ? const MraCard(child: SkeletonCard())
                  : TrackingTrendCard(
                      chartKey: const Key('secondaryTrendChart'),
                      title: _secondaryMetricLabel(_secondaryMetric),
                      tooltip: _secondaryMetricTooltip(_secondaryMetric),
                      series: _secondarySeries!,
                      formatValue: _secondaryMetricFormatter(_secondaryMetric),
                      color: theme.colorScheme.secondary,
                    ),
              const SizedBox(height: MraSpacing.xl),
              Text('Breakdown', style: theme.textTheme.titleMedium),
              const SizedBox(height: MraSpacing.sm),
              _buildDimensionSelector(),
              const SizedBox(height: MraSpacing.sm),
              _breakdownLoading
                  ? const MraCard(child: SkeletonCard())
                  : _buildBreakdownCards(context),
              const SizedBox(height: MraSpacing.xl),
              Text(
                'Recent closed predictions',
                style: theme.textTheme.titleMedium,
              ),
              const SizedBox(height: MraSpacing.sm),
              _buildPredictionsTable(context),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildRangeSelector() {
    // A custom from/to window (set via the Filters sheet's date-range
    // picker) takes precedence over the quick-range chips (AC/UX Rule:
    // "filters and date range"); none of the quick chips show selected in
    // that state since the effective window isn't any of them.
    final hasCustomRange = _filters.from != null && _filters.to != null;
    return Semantics(
      container: true,
      label: 'Date range selector',
      child: Wrap(
        spacing: MraSpacing.sm,
        children: [
          ..._ranges.map(
            (r) => ChoiceChip(
              label: Text(_rangeLabel(r)),
              selected: !hasCustomRange && r == _range,
              onSelected: (_) => _onRangeChanged(r),
            ),
          ),
          ChoiceChip(
            label: Text(
              hasCustomRange
                  ? '${_fmtDate(_filters.from!)} – ${_fmtDate(_filters.to!)}'
                  : 'Custom…',
            ),
            avatar: const Icon(Icons.date_range, size: 16),
            selected: hasCustomRange,
            onSelected: (_) => _pickCustomDateRange(),
          ),
        ],
      ),
    );
  }

  Widget _buildFiltersRow(BuildContext context) {
    return Row(
      children: [
        OutlinedButton.icon(
          onPressed: () => _openFiltersSheet(context),
          icon: const Icon(Icons.filter_list),
          label: Text(
            _filters.activeCount == 0
                ? 'Filters'
                : 'Filters (${_filters.activeCount})',
          ),
        ),
      ],
    );
  }

  void _openFiltersSheet(BuildContext context) {
    _sectorController.text = _filters.sector ?? '';
    _symbolController.text = _filters.symbol ?? '';
    showMraBottomSheet(
      context: context,
      title: 'Filters',
      builder: (sheetContext) => StatefulBuilder(
        builder: (sheetContext, setSheetState) {
          void apply(TrackingFilters Function() update) {
            setState(() => _filters = update());
            setSheetState(() {});
            _onFiltersChanged();
          }

          return SingleChildScrollView(
            child: buildTrackingFilterSheetBody(
              sheetContext: sheetContext,
              filters: _filters,
              sectorController: _sectorController,
              symbolController: _symbolController,
              actions: TrackingFilterSheetActions(
                apply: apply,
                onSectorChanged: (value) {
                  setSheetState(() {});
                  setState(() {
                    final trimmed = value.trim();
                    _filters = _filters.copyWith(
                      sector: trimmed.isEmpty ? null : trimmed,
                      clearSector: trimmed.isEmpty,
                    );
                  });
                  _debouncedFiltersChanged();
                },
                onSymbolChanged: (value) {
                  setSheetState(() {});
                  setState(() {
                    final trimmed = value.trim();
                    _filters = _filters.copyWith(
                      symbol: trimmed.isEmpty ? null : trimmed,
                      clearSymbol: trimmed.isEmpty,
                    );
                  });
                  _debouncedFiltersChanged();
                },
                onTextSubmitted: _onFiltersChanged,
                clearAll: () {
                  _sectorController.clear();
                  _symbolController.clear();
                  apply(() => const TrackingFilters());
                },
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _buildSecondaryMetricSelector() {
    return Semantics(
      container: true,
      label: 'Secondary outcome metric selector',
      child: Wrap(
        spacing: MraSpacing.sm,
        children: _secondaryMetrics
            .map(
              (m) => ChoiceChip(
                label: Text(_secondaryMetricChipLabel(m)),
                selected: m == _secondaryMetric,
                onSelected: (_) => _onSecondaryMetricChanged(m),
              ),
            )
            .toList(),
      ),
    );
  }

  Widget _buildDimensionSelector() {
    return Semantics(
      container: true,
      label: 'Breakdown dimension selector',
      child: Wrap(
        spacing: MraSpacing.sm,
        children: _dimensions
            .map(
              (d) => ChoiceChip(
                label: Text(_dimensionLabel(d)),
                selected: d == _dimension,
                onSelected: (_) => _onDimensionChanged(d),
              ),
            )
            .toList(),
      ),
    );
  }

  Widget _buildKpiGrid(TrackingSummary s) {
    Widget card(
      String label,
      String value, {
      String? delta,
      bool deltaPositive = true,
      IconData? icon,
    }) => SizedBox(
      width: 180,
      child: KpiStatCard(
        label: label,
        value: value,
        icon: icon,
        delta: delta,
        deltaPositive: deltaPositive,
      ),
    );

    return Wrap(
      spacing: MraSpacing.sm,
      runSpacing: MraSpacing.sm,
      children: [
        card('Active', s.activeCount.toString(), icon: Icons.hourglass_empty),
        card(
          'Closed',
          s.closedCount.toString(),
          icon: Icons.check_circle_outline,
        ),
        card(
          'Target hit rate',
          _fmtPct(s.targetHitRate),
          icon: Icons.flag_outlined,
        ),
        card(
          'Avg realized return',
          _fmtPct(s.avgRealizedReturn),
          icon: Icons.trending_up,
        ),
        card(
          'Avg predicted return',
          _fmtPct(s.avgPredictedReturn),
          icon: Icons.insights_outlined,
        ),
        card(
          'Trust score',
          _fmtPct(s.trustScore),
          delta: s.trustDelta == null
              ? null
              : '${s.trustDelta! >= 0 ? '+' : ''}'
                    '${(s.trustDelta! * 100).toStringAsFixed(1)}pp',
          deltaPositive: (s.trustDelta ?? 0) >= 0,
          icon: Icons.verified_outlined,
        ),
      ],
    );
  }

  /// EPIC-M3.8 — "Active positions": a compact live view of active
  /// positive recommendations (current price/target/SL distance, horizon
  /// remaining, Trust/freshness, M1.119-sourced status), independent of
  /// the historical "Recent closed predictions" table below.
  Widget _buildActiveSection(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                'Active positions',
                style: theme.textTheme.titleMedium,
              ),
            ),
            if (_activeFetchedAt != null)
              Text(
                'Updated ${ActivePredictionCard.formatRelativeTime(_activeFetchedAt)}',
                style: theme.textTheme.labelSmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            IconButton(
              tooltip: 'Refresh active positions',
              icon: const Icon(Icons.refresh, size: 20),
              onPressed: _loadActive,
            ),
          ],
        ),
        const SizedBox(height: MraSpacing.xs),
        Semantics(
          container: true,
          label: 'Auto-refresh interval selector',
          child: Wrap(
            spacing: MraSpacing.sm,
            children: _refreshIntervals.keys
                .map(
                  (label) => ChoiceChip(
                    label: Text(label),
                    selected: label == _refreshLabel,
                    onSelected: (_) => _onRefreshLabelChanged(label),
                  ),
                )
                .toList(),
          ),
        ),
        const SizedBox(height: MraSpacing.sm),
        if (_activeLoading && _activePredictions.isEmpty)
          const MraCard(child: SkeletonCard())
        else if (_activeError != null && _activePredictions.isEmpty)
          MraStateView.error(
            message: _activeError?.message,
            onAction: _loadActive,
          )
        else if (_activePredictions.isEmpty)
          const MraStateView.empty(message: 'No active positions right now.')
        else
          _buildActiveGrid(context),
      ],
    );
  }

  Widget _buildActiveGrid(BuildContext context) {
    return Column(
      children: [
        LayoutBuilder(
          builder: (context, constraints) {
            final columns = constraints.maxWidth >= 900
                ? 3
                : (constraints.maxWidth >= 600 ? 2 : 1);
            final cardWidth =
                (constraints.maxWidth - MraSpacing.sm * (columns - 1)) /
                columns;
            return Wrap(
              spacing: MraSpacing.sm,
              runSpacing: MraSpacing.sm,
              children: _activePredictions
                  .map(
                    (item) => SizedBox(
                      width: cardWidth,
                      child: ActivePredictionCard(
                        prediction: item,
                        onTap: () => _openActivePredictionDetail(item),
                      ),
                    ),
                  )
                  .toList(),
            );
          },
        ),
        const SizedBox(height: MraSpacing.md),
        if (_loadingMoreActive)
          const SizedBox(
            width: 24,
            height: 24,
            child: CircularProgressIndicator(strokeWidth: 2),
          )
        else if (_activeCursor != null)
          OutlinedButton(
            onPressed: _loadMoreActive,
            child: const Text('Load more'),
          ),
      ],
    );
  }

  Widget _buildBreakdownCards(BuildContext context) {
    final theme = Theme.of(context);
    final items = _breakdown?.items ?? const [];
    if (items.isEmpty) {
      return const MraStateView.empty(
        message: 'No breakdown data for this dimension yet.',
      );
    }
    return Wrap(
      spacing: MraSpacing.sm,
      runSpacing: MraSpacing.sm,
      children: items.map((item) {
        return SizedBox(
          width: 220,
          child: MraCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        item.key,
                        style: theme.textTheme.labelLarge,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    if (item.smallSample)
                      Tooltip(
                        message: 'Small sample — rates may be volatile',
                        child: Icon(
                          Icons.warning_amber_outlined,
                          size: 16,
                          color: theme.colorScheme.error,
                        ),
                      ),
                  ],
                ),
                const SizedBox(height: MraSpacing.xs),
                Text(
                  'n=${item.predictionCount} · ${item.closedCount} closed',
                  style: theme.textTheme.labelSmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
                const SizedBox(height: MraSpacing.sm),
                Text(
                  'Target hit: ${_fmtPct(item.targetHitRate)}',
                  style: theme.textTheme.bodySmall,
                ),
                Text(
                  'Avg return: ${_fmtPct(item.avgRealizedReturn)}',
                  style: theme.textTheme.bodySmall,
                ),
              ],
            ),
          ),
        );
      }).toList(),
    );
  }

  Widget _buildPredictionsTable(BuildContext context) => ClosedPredictionsTable(
    predictions: _predictions,
    loadingMore: _loadingMorePredictions,
    cursor: _predictionsCursor,
    onLoadMore: _loadMorePredictions,
    rowRoute: (id) => '/tracking/recommendation/$id',
  );

  static String _fmtPct(double? v) =>
      v == null ? '—' : '${(v * 100).toStringAsFixed(1)}%';

  static String _fmtPctValue(double v) => '${(v * 100).toStringAsFixed(1)}%';

  static String _fmtPpValue(double v) => '${(v * 100).toStringAsFixed(1)}pp';

  static String _fmtDate(DateTime d) =>
      '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

  static String _rangeLabel(String r) => switch (r) {
    '7d' => '7 days',
    '30d' => '30 days',
    '90d' => '90 days',
    '1y' => '1 year',
    _ => r,
  };

  static String _dimensionLabel(String d) => switch (d) {
    'horizon' => 'Horizon',
    'sector' => 'Sector',
    'marketCap' => 'Market cap',
    'regime' => 'Regime',
    'setup' => 'Setup',
    'stock' => 'Stock',
    _ => d,
  };

  static String _secondaryMetricLabel(String m) => switch (m) {
    'hitRate' => 'Target-hit rate trend',
    'return' => 'Realized return trend',
    'calibration' => 'Calibration error trend',
    _ => m,
  };

  // Distinct from _secondaryMetricLabel: the chip is a selector, not the
  // chart's own title, so it drops the "trend" suffix (also avoids the two
  // rendering identically and colliding in text-based tests/finders).
  static String _secondaryMetricChipLabel(String m) => switch (m) {
    'hitRate' => 'Target-hit rate',
    'return' => 'Realized return',
    'calibration' => 'Calibration error',
    _ => m,
  };

  static String _secondaryMetricTooltip(String m) => switch (m) {
    'hitRate' =>
      'Share of closed predictions in each period that reached their '
          'target price before a stop-loss or horizon expiry.',
    'return' => 'Average realized return of closed predictions in each period.',
    'calibration' =>
      'Average confidence-calibration error — how far predicted '
          'probabilities were from real outcomes. Lower is better.',
    _ => '',
  };

  static String Function(double) _secondaryMetricFormatter(String m) =>
      m == 'calibration' ? _fmtPpValue : _fmtPctValue;
}

enum _DetailLoadState { loading, error, loaded }

/// EPIC-M3.8 — the `/predictions/active/{predictionId}` drill-down sheet.
/// Always re-fetches fresh data from the server (never just re-renders the
/// list's own snapshot) so a tap always reflects the latest server
/// freshness, falling back to the list item's already-known fields only if
/// that re-fetch fails.
class _ActivePredictionDetailSheet extends StatefulWidget {
  final TrackingRepository repository;
  final int predictionId;
  final ActivePrediction fallback;

  const _ActivePredictionDetailSheet({
    required this.repository,
    required this.predictionId,
    required this.fallback,
  });

  @override
  State<_ActivePredictionDetailSheet> createState() =>
      _ActivePredictionDetailSheetState();
}

class _ActivePredictionDetailSheetState
    extends State<_ActivePredictionDetailSheet> {
  _DetailLoadState _state = _DetailLoadState.loading;
  ActivePrediction? _prediction;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _state = _DetailLoadState.loading);
    try {
      final prediction = await widget.repository.fetchActivePrediction(
        widget.predictionId,
      );
      setState(() {
        _prediction = prediction;
        _state = _DetailLoadState.loaded;
      });
    } catch (_) {
      // Keep the list's already-known snapshot visible rather than an
      // empty sheet -- it is stale but real data, not fabricated.
      setState(() {
        _prediction = widget.fallback;
        _state = _DetailLoadState.error;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_state == _DetailLoadState.loading && _prediction == null) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: MraSpacing.lg),
        child: Center(child: CircularProgressIndicator()),
      );
    }
    final prediction = _prediction!;
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (_state == _DetailLoadState.error)
          Padding(
            padding: const EdgeInsets.only(bottom: MraSpacing.sm),
            child: MraChip(
              label: 'Showing last known data — refresh failed',
              tone: MraChipTone.warning,
              icon: Icons.warning_amber_outlined,
            ),
          ),
        ActivePredictionCard(prediction: prediction),
        if (prediction.nextEvaluationAt != null) ...[
          const SizedBox(height: MraSpacing.sm),
          Text(
            'Next evaluation: ${prediction.nextEvaluationAt}',
            style: Theme.of(context).textTheme.labelSmall,
          ),
        ],
      ],
    );
  }
}
