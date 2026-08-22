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
///
/// EPIC-M3.16 follow-up — an option set long enough to overflow the bar's
/// width (e.g. Tracking/History's 7-option Regime row) relied on the
/// platform's default (desktop/web-only, easy-to-miss) scrollbar as the
/// only sign more chips existed; an explicit, always-visible [Scrollbar]
/// makes that affordance obvious everywhere, including touch platforms.
class MraFilterBar extends StatefulWidget {
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
  State<MraFilterBar> createState() => _MraFilterBarState();
}

class _MraFilterBarState extends State<MraFilterBar> {
  final _scrollController = ScrollController();

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 40,
      child: Scrollbar(
        controller: _scrollController,
        thumbVisibility: true,
        child: ListView.separated(
          controller: _scrollController,
          scrollDirection: Axis.horizontal,
          itemCount: widget.options.length,
          separatorBuilder: (context, index) =>
              const SizedBox(width: MraSpacing.sm),
          itemBuilder: (context, index) {
            final option = widget.options[index];
            final selected = widget.selectedIds.contains(option.id);
            return MraChip(
              label: option.label,
              selected: selected,
              tone: selected ? MraChipTone.info : MraChipTone.neutral,
              onTap: () => widget.onToggle(option.id),
            );
          },
        ),
      ),
    );
  }
}
