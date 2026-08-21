import 'package:flutter/material.dart';

import '../tokens/mra_spacing.dart';

class MraColumn {
  final String label;
  final Alignment alignment;
  const MraColumn(this.label, {this.alignment = Alignment.centerLeft});
}

/// EPIC-M1.133 — dense data grid/table for desktop/wide layouts (e.g.
/// recommendation table view). Rows are plain widgets so callers can put
/// any cell content (chips, sparklines, badges) inside.
class MraDenseTable extends StatelessWidget {
  final List<MraColumn> columns;
  final List<List<Widget>> rows;
  final void Function(int rowIndex)? onRowTap;

  const MraDenseTable({
    super.key,
    required this.columns,
    required this.rows,
    this.onRowTap,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Container(
          padding: const EdgeInsets.symmetric(
            horizontal: MraSpacing.md,
            vertical: MraSpacing.sm,
          ),
          decoration: BoxDecoration(
            color: theme.colorScheme.surfaceContainerLow,
            border: Border(
              bottom: BorderSide(color: theme.colorScheme.outlineVariant),
            ),
          ),
          child: Row(
            children: columns
                .map(
                  (c) => Expanded(
                    child: Align(
                      alignment: c.alignment,
                      child: Text(
                        c.label,
                        style: theme.textTheme.labelSmall?.copyWith(
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                      ),
                    ),
                  ),
                )
                .toList(),
          ),
        ),
        ...List.generate(rows.length, (rowIndex) {
          final cells = rows[rowIndex];
          return InkWell(
            onTap: onRowTap == null ? null : () => onRowTap!(rowIndex),
            child: Container(
              padding: const EdgeInsets.symmetric(
                horizontal: MraSpacing.md,
                vertical: MraSpacing.sm,
              ),
              decoration: BoxDecoration(
                border: Border(
                  bottom: BorderSide(
                    color: theme.colorScheme.outlineVariant.withValues(
                      alpha: 0.5,
                    ),
                  ),
                ),
              ),
              child: Row(
                children: cells
                    .asMap()
                    .entries
                    .map(
                      (entry) => Expanded(
                        child: Align(
                          alignment: columns[entry.key].alignment,
                          child: entry.value,
                        ),
                      ),
                    )
                    .toList(),
              ),
            ),
          );
        }),
      ],
    );
  }
}
