import 'package:flutter/material.dart';

import '../tokens/mra_spacing.dart';
import 'mra_card.dart';

/// EPIC-M3.4 — a titled, collapsible card section. Used to keep dense
/// detail screens (e.g. recommendation detail's evidence/events panels)
/// uncluttered via progressive disclosure: the most important information
/// stays outside this widget (always visible), while supplementary detail
/// lives inside and can be tucked away without leaving the screen.
class MraExpandableSection extends StatefulWidget {
  final String title;
  final Widget child;
  final bool initiallyExpanded;

  const MraExpandableSection({
    super.key,
    required this.title,
    required this.child,
    this.initiallyExpanded = true,
  });

  @override
  State<MraExpandableSection> createState() => _MraExpandableSectionState();
}

class _MraExpandableSectionState extends State<MraExpandableSection> {
  late bool _expanded = widget.initiallyExpanded;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return MraCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          InkWell(
            onTap: () => setState(() => _expanded = !_expanded),
            child: Semantics(
              button: true,
              expanded: _expanded,
              label: widget.title,
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Expanded(
                    child: Text(
                      widget.title,
                      style: theme.textTheme.titleMedium,
                    ),
                  ),
                  Icon(_expanded ? Icons.expand_less : Icons.expand_more),
                ],
              ),
            ),
          ),
          if (_expanded) ...[
            const SizedBox(height: MraSpacing.md),
            widget.child,
          ],
        ],
      ),
    );
  }
}
