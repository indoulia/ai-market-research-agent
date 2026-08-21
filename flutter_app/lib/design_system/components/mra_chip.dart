import 'package:flutter/material.dart';

import '../tokens/mra_colors.dart';

enum MraChipTone { neutral, positive, warning, error, info }

/// EPIC-M1.133 — shared chip/tag component. Tone conveys meaning via both
/// color and an optional leading icon, never color alone.
class MraChip extends StatelessWidget {
  final String label;
  final MraChipTone tone;
  final IconData? icon;
  final bool selected;
  final VoidCallback? onTap;

  const MraChip({
    super.key,
    required this.label,
    this.tone = MraChipTone.neutral,
    this.icon,
    this.selected = false,
    this.onTap,
  });

  _ToneColors _colorsFor(BuildContext context) {
    final scheme = MraColorScheme.of(context);
    final theme = Theme.of(context);
    switch (tone) {
      case MraChipTone.positive:
        return _ToneColors(scheme.positiveContainer, scheme.positive);
      case MraChipTone.warning:
        return _ToneColors(scheme.warningContainer, scheme.warning);
      case MraChipTone.error:
        return _ToneColors(scheme.errorContainer, scheme.error);
      case MraChipTone.info:
        return _ToneColors(scheme.infoContainer, scheme.info);
      case MraChipTone.neutral:
        return _ToneColors(
          theme.colorScheme.surfaceContainerHigh,
          theme.colorScheme.onSurfaceVariant,
        );
    }
  }

  @override
  Widget build(BuildContext context) {
    final colors = _colorsFor(context);
    final textStyle = Theme.of(
      context,
    ).textTheme.labelMedium?.copyWith(color: colors.foreground);

    final content = Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (icon != null) ...[
          Icon(icon, size: 14, color: colors.foreground),
          const SizedBox(width: 4),
        ],
        Text(label, style: textStyle),
      ],
    );

    return Semantics(
      button: onTap != null,
      selected: selected,
      label: label,
      child: Material(
        color: colors.background,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(999),
          side: selected
              ? BorderSide(color: colors.foreground, width: 1.2)
              : BorderSide.none,
        ),
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(999),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
            child: content,
          ),
        ),
      ),
    );
  }
}

class _ToneColors {
  final Color background;
  final Color foreground;
  const _ToneColors(this.background, this.foreground);
}
