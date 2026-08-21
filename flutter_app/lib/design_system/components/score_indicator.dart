import 'package:flutter/material.dart';

import '../tokens/mra_colors.dart';
import '../tokens/mra_spacing.dart';

enum MraScoreKind { score, confidence, trust }

/// EPIC-M1.133 — compact score/confidence/trust indicator: a labelled
/// circular gauge. Value is always accompanied by digits and a text label,
/// never color/fill alone, so it reads correctly without color vision.
class ScoreIndicator extends StatelessWidget {
  final MraScoreKind kind;
  final double value0to100;
  final double size;

  const ScoreIndicator({
    super.key,
    required this.kind,
    required this.value0to100,
    this.size = 44,
  });

  String get _label {
    switch (kind) {
      case MraScoreKind.score:
        return 'Score';
      case MraScoreKind.confidence:
        return 'Confidence';
      case MraScoreKind.trust:
        return 'Trust';
    }
  }

  Color _colorFor(BuildContext context) {
    final scheme = MraColorScheme.of(context);
    if (value0to100 >= 70) return scheme.positive;
    if (value0to100 >= 40) return scheme.warning;
    return scheme.error;
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final color = _colorFor(context);
    final clamped = value0to100.clamp(0, 100).toDouble();

    return Semantics(
      label: '$_label ${clamped.round()} out of 100',
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          SizedBox(
            width: size,
            height: size,
            child: Stack(
              alignment: Alignment.center,
              children: [
                SizedBox(
                  width: size,
                  height: size,
                  child: CircularProgressIndicator(
                    value: clamped / 100,
                    strokeWidth: 4,
                    backgroundColor: theme.colorScheme.surfaceContainerHigh,
                    valueColor: AlwaysStoppedAnimation<Color>(color),
                  ),
                ),
                Text(
                  clamped.round().toString(),
                  style: theme.textTheme.labelLarge?.copyWith(color: color),
                ),
              ],
            ),
          ),
          const SizedBox(height: MraSpacing.xs),
          Text(_label, style: theme.textTheme.labelSmall),
        ],
      ),
    );
  }
}
