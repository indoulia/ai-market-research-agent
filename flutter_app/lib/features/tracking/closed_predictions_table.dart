import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../design_system/design_system.dart';
import 'tracked_prediction.dart';

/// EPIC-172 — the closed-predictions table + "Load more" footer, shared
/// by [TrackingScreen]'s "Recent closed predictions" section and the
/// standalone `/history` screen (both list the same
/// `/tracking/predictions?status=closed` data; only the surrounding page
/// chrome differs).
class ClosedPredictionsTable extends StatelessWidget {
  final List<TrackedPrediction> predictions;
  final bool loadingMore;
  final String? cursor;
  final VoidCallback onLoadMore;
  final String Function(int id) rowRoute;

  const ClosedPredictionsTable({
    super.key,
    required this.predictions,
    required this.loadingMore,
    required this.cursor,
    required this.onLoadMore,
    required this.rowRoute,
  });

  static String _fmtPct(double? v) =>
      v == null ? '—' : '${(v * 100).toStringAsFixed(1)}%';

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    if (predictions.isEmpty) {
      return const MraStateView.empty(message: 'No closed predictions yet.');
    }
    return Column(
      children: [
        MraDenseTable(
          columns: const [
            MraColumn('Symbol'),
            MraColumn('Horizon', alignment: Alignment.centerRight),
            MraColumn('Predicted', alignment: Alignment.centerRight),
            MraColumn('Realized', alignment: Alignment.centerRight),
            MraColumn('Outcome', alignment: Alignment.centerRight),
          ],
          rows: predictions
              .map(
                (p) => [
                  Text(p.symbol, maxLines: 1, overflow: TextOverflow.ellipsis),
                  Text('${p.horizonDays}D', textAlign: TextAlign.right),
                  Text(_fmtPct(p.predictedReturn), textAlign: TextAlign.right),
                  Text(
                    p.realizedReturn == null ? '—' : _fmtPct(p.realizedReturn),
                    textAlign: TextAlign.right,
                  ),
                  Text(p.outcome ?? '—', textAlign: TextAlign.right),
                ],
              )
              .toList(),
          onRowTap: (index) => context.push(rowRoute(predictions[index].id)),
        ),
        const SizedBox(height: MraSpacing.md),
        Center(
          child: loadingMore
              ? const SizedBox(
                  width: 24,
                  height: 24,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : (cursor == null
                    ? Text(
                        'You’re all caught up',
                        style: theme.textTheme.labelSmall,
                      )
                    : OutlinedButton(
                        onPressed: onLoadMore,
                        child: const Text('Load more'),
                      )),
        ),
      ],
    );
  }
}
