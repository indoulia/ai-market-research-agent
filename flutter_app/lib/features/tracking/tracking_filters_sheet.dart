import 'package:flutter/material.dart';

import '../../design_system/design_system.dart';
import 'tracking_filters.dart';

// EPIC-M3.15 — filter option sets. `horizon`/`marketCap` mirror the real,
// fixed product/policy values `app/horizon.py` (1/3/5/7-day horizon
// selection) and `app/discovery_segmentation.py` (market-cap buckets)
// already use elsewhere (e.g. Opportunity Explorer's own filter sheet).
// `regime` mirrors `app/market_regime.py`'s real, fixed trend x volatility
// classification -- not a fabricated taxonomy. EPIC-172 made these
// public (was tracking_screen.dart-private) so the standalone `/history`
// screen's filter sheet can share the exact same option lists.
const kTrackingHorizonFilterOptions = [
  MraFilterOption('ALL', 'All horizons'),
  MraFilterOption('1', '1D'),
  MraFilterOption('3', '3D'),
  MraFilterOption('5', '5D'),
  MraFilterOption('7', '7D'),
];

const kTrackingMarketCapFilterOptions = [
  MraFilterOption('ALL', 'All sizes'),
  MraFilterOption('LARGE_CAP', 'Large cap'),
  MraFilterOption('MID_CAP', 'Mid cap'),
  MraFilterOption('SMALL_CAP', 'Small cap'),
];

const kTrackingRegimeFilterOptions = [
  MraFilterOption('ALL', 'All regimes'),
  MraFilterOption('BULLISH_HIGH_VOL', 'Bullish · high vol'),
  MraFilterOption('BULLISH_LOW_VOL', 'Bullish · low vol'),
  MraFilterOption('NEUTRAL_HIGH_VOL', 'Neutral · high vol'),
  MraFilterOption('NEUTRAL_LOW_VOL', 'Neutral · low vol'),
  MraFilterOption('BEARISH_HIGH_VOL', 'Bearish · high vol'),
  MraFilterOption('BEARISH_LOW_VOL', 'Bearish · low vol'),
];

/// EPIC-172 — the callbacks [buildTrackingFilterSheetBody] needs to mutate
/// a *host screen's own* [TrackingFilters] state without owning it, so the
/// same sheet body can back both [TrackingScreen] and the `/history` screen.
class TrackingFilterSheetActions {
  /// Chip toggles + "Clear all": update filters and reload immediately.
  final void Function(TrackingFilters Function() update) apply;
  final void Function(String value) onSectorChanged;
  final void Function(String value) onSymbolChanged;
  final VoidCallback onTextSubmitted;
  final VoidCallback clearAll;

  const TrackingFilterSheetActions({
    required this.apply,
    required this.onSectorChanged,
    required this.onSymbolChanged,
    required this.onTextSubmitted,
    required this.clearAll,
  });
}

/// EPIC-172 — extracted from [TrackingScreen]'s `_openFiltersSheet` so the
/// `/history` screen (also filtering `/tracking/predictions?status=closed`)
/// gets the identical horizon/market-cap/regime/sector/symbol filter UI
/// instead of a second, drift-prone copy. The host screen wraps this in its
/// own `showMraBottomSheet` + `StatefulBuilder` so `filters` and `actions`
/// stay bound to its own state.
Widget buildTrackingFilterSheetBody({
  required BuildContext sheetContext,
  required TrackingFilters filters,
  required TextEditingController sectorController,
  required TextEditingController symbolController,
  required TrackingFilterSheetActions actions,
}) {
  final labelStyle = Theme.of(sheetContext).textTheme.labelMedium;
  return Column(
    mainAxisSize: MainAxisSize.min,
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text('Horizon', style: labelStyle),
      const SizedBox(height: MraSpacing.xs),
      MraFilterBar(
        key: const Key('trackingHorizonFilter'),
        options: kTrackingHorizonFilterOptions,
        selectedIds: {filters.horizon?.toString() ?? 'ALL'},
        onToggle: (id) => actions.apply(
          () => filters.copyWith(
            horizon: id == 'ALL' ? null : int.parse(id),
            clearHorizon: id == 'ALL',
          ),
        ),
      ),
      const SizedBox(height: MraSpacing.md),
      Text('Market cap', style: labelStyle),
      const SizedBox(height: MraSpacing.xs),
      MraFilterBar(
        key: const Key('trackingMarketCapFilter'),
        options: kTrackingMarketCapFilterOptions,
        selectedIds: {filters.marketCap ?? 'ALL'},
        onToggle: (id) => actions.apply(
          () => filters.copyWith(
            marketCap: id == 'ALL' ? null : id,
            clearMarketCap: id == 'ALL',
          ),
        ),
      ),
      const SizedBox(height: MraSpacing.md),
      Text('Regime', style: labelStyle),
      const SizedBox(height: MraSpacing.xs),
      MraFilterBar(
        key: const Key('trackingRegimeFilter'),
        options: kTrackingRegimeFilterOptions,
        selectedIds: {filters.regime ?? 'ALL'},
        onToggle: (id) => actions.apply(
          () => filters.copyWith(
            regime: id == 'ALL' ? null : id,
            clearRegime: id == 'ALL',
          ),
        ),
      ),
      const SizedBox(height: MraSpacing.md),
      Row(
        children: [
          Expanded(
            child: TextField(
              controller: sectorController,
              decoration: const InputDecoration(
                labelText: 'Sector',
                isDense: true,
              ),
              onSubmitted: (_) => actions.onTextSubmitted(),
              onChanged: actions.onSectorChanged,
            ),
          ),
          const SizedBox(width: MraSpacing.md),
          Expanded(
            child: TextField(
              controller: symbolController,
              decoration: const InputDecoration(
                labelText: 'Symbol',
                isDense: true,
              ),
              onSubmitted: (_) => actions.onTextSubmitted(),
              onChanged: actions.onSymbolChanged,
            ),
          ),
        ],
      ),
      const SizedBox(height: MraSpacing.md),
      Align(
        alignment: Alignment.centerRight,
        child: TextButton(
          onPressed: actions.clearAll,
          child: const Text('Clear all filters'),
        ),
      ),
    ],
  );
}
