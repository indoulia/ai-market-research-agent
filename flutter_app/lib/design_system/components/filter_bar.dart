import 'package:flutter/material.dart';

import '../tokens/mra_spacing.dart';
import 'mra_chip.dart';

class MraFilterOption {
  final String id;
  final String label;
  const MraFilterOption(this.id, this.label);
}

/// EPIC-M1.133 — horizontally scrollable filter bar of toggle chips, shared
/// by every screen with filterable collections (recommendations, discovery,
/// news). Mobile screens may present the same options inside a bottom sheet
/// via [MraFilterOption]; this widget only renders the inline chip row.
class MraFilterBar extends StatelessWidget {
  final List<MraFilterOption> options;
  final Set<String> selectedIds;
  final ValueChanged<String> onToggle;

  const MraFilterBar({
    super.key,
    required this.options,
    required this.selectedIds,
    required this.onToggle,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 40,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: options.length,
        separatorBuilder: (context, index) =>
            const SizedBox(width: MraSpacing.sm),
        itemBuilder: (context, index) {
          final option = options[index];
          final selected = selectedIds.contains(option.id);
          return MraChip(
            label: option.label,
            selected: selected,
            tone: selected ? MraChipTone.info : MraChipTone.neutral,
            onTap: () => onToggle(option.id),
          );
        },
      ),
    );
  }
}
