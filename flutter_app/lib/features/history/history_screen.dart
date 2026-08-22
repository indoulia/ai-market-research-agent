import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api_exception.dart';
import '../../design_system/design_system.dart';
import '../tracking/closed_predictions_table.dart';
import '../tracking/tracked_prediction.dart';
import '../tracking/tracking_filters.dart';
import '../tracking/tracking_filters_sheet.dart';
import '../tracking/tracking_repository.dart';

enum _LoadState { loading, error, loaded }

/// EPIC-M3.17 — the `/history` destination: a focused, full-page list of
/// resolved (closed) recommendations. Reuses EPIC-M1.147/M3.15's real,
/// already-merged `/tracking/predictions?status=closed` data layer as-is
/// (`TrackingRepository`, `TrackedPrediction`, `TrackingFilters`) rather
/// than duplicating it — no new backend work needed. Deliberately omits
/// Tracking's KPI grid/trend charts/breakdown: those are Tracking's own
/// performance-analytics concern, distinct from a plain history list.
class HistoryScreen extends StatefulWidget {
  const HistoryScreen({super.key, TrackingRepository? repository})
    : _repository = repository;

  final TrackingRepository? _repository;

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  late final TrackingRepository _repository =
      widget._repository ?? TrackingRepository();

  _LoadState _state = _LoadState.loading;
  ApiException? _error;
  TrackingFilters _filters = const TrackingFilters();
  List<TrackedPrediction> _predictions = [];
  String? _cursor;
  bool _loadingMore = false;
  Timer? _filterDebounce;

  final _sectorController = TextEditingController();
  final _symbolController = TextEditingController();

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _filterDebounce?.cancel();
    _sectorController.dispose();
    _symbolController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() => _state = _LoadState.loading);
    try {
      final page = await _repository.fetchPredictions(
        status: 'closed',
        filters: _filters,
      );
      setState(() {
        _predictions = page.items;
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
      final page = await _repository.fetchPredictions(
        status: 'closed',
        cursor: _cursor,
        filters: _filters,
      );
      setState(() {
        _predictions = [..._predictions, ...page.items];
        _cursor = page.nextCursor;
        _loadingMore = false;
      });
    } catch (_) {
      setState(() => _loadingMore = false);
    }
  }

  void _debouncedReload() {
    _filterDebounce?.cancel();
    _filterDebounce = Timer(const Duration(milliseconds: 350), _load);
  }

  void _openFiltersSheet(BuildContext context) {
    _sectorController.text = _filters.sector ?? '';
    _symbolController.text = _filters.symbol ?? '';
    showMraBottomSheet<void>(
      context: context,
      title: 'Filters',
      builder: (sheetContext) => StatefulBuilder(
        builder: (sheetContext, setSheetState) {
          void apply(TrackingFilters Function() update) {
            setState(() => _filters = update());
            setSheetState(() {});
            _load();
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
                  _debouncedReload();
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
                  _debouncedReload();
                },
                onTextSubmitted: _load,
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
                      'History',
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
              Align(
                alignment: Alignment.centerLeft,
                child: OutlinedButton.icon(
                  onPressed: () => _openFiltersSheet(context),
                  icon: const Icon(Icons.filter_list),
                  label: Text(
                    _filters.activeCount == 0
                        ? 'Filters'
                        : 'Filters (${_filters.activeCount})',
                  ),
                ),
              ),
              const SizedBox(height: MraSpacing.lg),
              ClosedPredictionsTable(
                predictions: _predictions,
                loadingMore: _loadingMore,
                cursor: _cursor,
                onLoadMore: _loadMore,
                rowRoute: (id) => '/history/recommendation/$id',
              ),
            ],
          ),
        ),
      ),
    );
  }
}
