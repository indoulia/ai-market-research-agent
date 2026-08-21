import 'package:flutter/material.dart';

import '../../design_system/design_system.dart';
import 'market_summary.dart';

/// EPIC-M1.140 — one row in the sector leaders/laggards grid.
class SectorMoveChip extends StatelessWidget {
  final SectorMove move;

  const SectorMoveChip({super.key, required this.move});

  @override
  Widget build(BuildContext context) {
    final isUp = move.averageChangePct >= 0;
    return MraChip(
      label:
          '${move.sector} ${isUp ? '+' : ''}${move.averageChangePct.toStringAsFixed(1)}%',
      tone: isUp ? MraChipTone.positive : MraChipTone.error,
      icon: isUp ? Icons.trending_up : Icons.trending_down,
    );
  }
}
