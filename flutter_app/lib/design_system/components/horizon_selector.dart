import 'package:flutter/material.dart';

import '../tokens/mra_spacing.dart';

/// EPIC-M1.133 — horizon selector (e.g. 1D/3D/5D/7D) used on dashboard and
/// detail screens. A single shared widget so horizon vocabulary/order never
/// drifts between screens.
class HorizonSelector extends StatelessWidget {
  final List<int> horizonsDays;
  final int selectedDays;
  final ValueChanged<int> onChanged;

  const HorizonSelector({
    super.key,
    required this.horizonsDays,
    required this.selectedDays,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Semantics(
      container: true,
      label: 'Horizon selector',
      child: Wrap(
        spacing: MraSpacing.sm,
        children: horizonsDays.map((days) {
          final selected = days == selectedDays;
          return ChoiceChip(
            label: Text('${days}D'),
            selected: selected,
            onSelected: (_) => onChanged(days),
            labelStyle: theme.textTheme.labelMedium?.copyWith(
              color: selected
                  ? theme.colorScheme.onSecondaryContainer
                  : theme.colorScheme.onSurfaceVariant,
            ),
          );
        }).toList(),
      ),
    );
  }
}
