import 'package:flutter/material.dart';

import '../../core/api_exception.dart';
import '../../design_system/design_system.dart';
import 'market_repository.dart';
import 'market_summary.dart';
import 'sector_move_row.dart';

enum _LoadState { loading, error, loaded }

/// EPIC-M1.140 — Market "Overview" tab: status/regime, breadth/volume/
/// volatility widgets, sector leaders/laggards. Compact index cards are
/// intentionally omitted — M1.139's `indexes` is always `[]` (no
/// index-level price feed exists yet); showing empty cards would be
/// decorative, not informative.
class MarketOverviewScreen extends StatefulWidget {
  final MarketRepository? repository;

  const MarketOverviewScreen({super.key, this.repository});

  @override
  State<MarketOverviewScreen> createState() => _MarketOverviewScreenState();
}

class _MarketOverviewScreenState extends State<MarketOverviewScreen> {
  late final MarketRepository _repository;
  _LoadState _state = _LoadState.loading;
  MarketSummary? _summary;
  ApiException? _error;

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? MarketRepository();
    _load();
  }

  Future<void> _load() async {
    setState(() => _state = _LoadState.loading);
    try {
      final summary = await _repository.fetchSummary();
      setState(() {
        _summary = summary;
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
        return _buildLoaded(context, _summary!);
    }
  }

  Widget _buildLoaded(BuildContext context, MarketSummary summary) {
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
                  MraChip(
                    label: summary.marketStatus == 'UNKNOWN'
                        ? 'Status unavailable'
                        : summary.marketStatus,
                    tone: MraChipTone.neutral,
                  ),
                  const SizedBox(width: MraSpacing.sm),
                  MraChip(
                    label: summary.regime ?? 'Regime unavailable',
                    tone: MraChipTone.info,
                  ),
                ],
              ),
              const SizedBox(height: MraSpacing.lg),
              Row(
                children: [
                  Expanded(
                    child: KpiStatCard(
                      label: 'Advance/Decline',
                      value: summary.advanceDecline ?? '—',
                      icon: Icons.compare_arrows,
                    ),
                  ),
                  const SizedBox(width: MraSpacing.sm),
                  Expanded(
                    child: KpiStatCard(
                      label: 'Volume',
                      value: summary.volume?.toString() ?? '—',
                      icon: Icons.bar_chart,
                    ),
                  ),
                  const SizedBox(width: MraSpacing.sm),
                  Expanded(
                    child: KpiStatCard(
                      label: 'Volatility',
                      value: summary.volatility?.toStringAsFixed(2) ?? '—',
                      icon: Icons.show_chart,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: MraSpacing.xl),
              Text('Sector leaders', style: theme.textTheme.titleMedium),
              const SizedBox(height: MraSpacing.sm),
              summary.sectorLeaders.isEmpty
                  ? Text(
                      'No sector data yet.',
                      style: theme.textTheme.bodySmall,
                    )
                  : Wrap(
                      spacing: MraSpacing.sm,
                      runSpacing: MraSpacing.sm,
                      children: summary.sectorLeaders
                          .map((m) => SectorMoveChip(move: m))
                          .toList(),
                    ),
              const SizedBox(height: MraSpacing.lg),
              Text('Sector laggards', style: theme.textTheme.titleMedium),
              const SizedBox(height: MraSpacing.sm),
              summary.sectorLaggards.isEmpty
                  ? Text(
                      'No sector data yet.',
                      style: theme.textTheme.bodySmall,
                    )
                  : Wrap(
                      spacing: MraSpacing.sm,
                      runSpacing: MraSpacing.sm,
                      children: summary.sectorLaggards
                          .map((m) => SectorMoveChip(move: m))
                          .toList(),
                    ),
            ],
          ),
        ),
      ),
    );
  }
}
