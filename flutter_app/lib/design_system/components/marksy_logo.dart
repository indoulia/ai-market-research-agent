import 'package:flutter/material.dart';

import '../tokens/mra_colors.dart';

/// EPIC-170 — the Marksy brand mark. The icon is a raster asset (see
/// docs/branding/marksy/README.md for provenance/limitations); the
/// "Marksy" wordmark is rendered as real text rather than a baked image so
/// it scales correctly at any text-scale factor and adapts to the active
/// theme's brightness automatically — matching every wordmark variant on
/// the approved reference board, which shows the wordmark as styled text,
/// not a fixed logotype graphic.
class MarksyWordmark extends StatelessWidget {
  final double fontSize;

  /// True when placed on a dark, non-theme-following surface (the navy
  /// app-bar chrome) rather than the app's own themed surface color.
  final bool light;

  const MarksyWordmark({super.key, this.fontSize = 20, this.light = false});

  @override
  Widget build(BuildContext context) {
    final onSurface = light
        ? MraColors.neutral0
        : Theme.of(context).colorScheme.onSurface;
    final baseStyle = TextStyle(
      fontSize: fontSize,
      fontWeight: FontWeight.w800,
      height: 1,
      letterSpacing: -0.2,
    );
    return Text.rich(
      TextSpan(
        children: [
          TextSpan(
            text: 'Mark',
            style: baseStyle.copyWith(color: onSurface),
          ),
          TextSpan(
            text: 'sy',
            style: baseStyle.copyWith(
              foreground: Paint()
                ..shader = const LinearGradient(
                  colors: [MraColors.brandPrimary, MraColors.brandTeal],
                ).createShader(Rect.fromLTWH(0, 0, fontSize * 1.2, fontSize)),
            ),
          ),
        ],
      ),
    );
  }
}

/// The icon-only mark (candlestick + growth arrow "M"), for compact nav,
/// launcher and favicon use. Uses the dark-badge asset by default since
/// most placements (app bar, nav rail) sit on the app's own surface color,
/// not literally on the reference board's dark card — see the README for
/// why a light-badge variant also ships for light-surface placements.
class MarksyIcon extends StatelessWidget {
  final double size;
  final bool light;

  const MarksyIcon({super.key, this.size = 28, this.light = false});

  @override
  Widget build(BuildContext context) {
    return Image.asset(
      light
          ? 'assets/branding/marksy-icon-light.png'
          : 'assets/branding/marksy-icon-dark.png',
      width: size,
      height: size,
    );
  }
}

/// Icon + wordmark lockup, for headers/app bars/nav rails.
class MarksyLogo extends StatelessWidget {
  final double iconSize;
  final double fontSize;

  /// True when placed on the navy app-bar chrome (or any other dark,
  /// non-theme-following surface) -- swaps both the icon badge and the
  /// wordmark's "Mark" text for their light-surface-legible variants.
  final bool light;

  const MarksyLogo({
    super.key,
    this.iconSize = 28,
    this.fontSize = 20,
    this.light = false,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        MarksyIcon(size: iconSize, light: light),
        const SizedBox(width: 8),
        MarksyWordmark(fontSize: fontSize, light: light),
      ],
    );
  }
}
