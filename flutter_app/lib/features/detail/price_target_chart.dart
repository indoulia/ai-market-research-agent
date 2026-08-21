import 'package:flutter/material.dart';

import '../../design_system/tokens/mra_colors.dart';
import '../../design_system/tokens/mra_spacing.dart';
import '../../design_system/tokens/mra_typography.dart';

class PricePoint {
  final DateTime timestamp;
  final double price;
  const PricePoint(this.timestamp, this.price);
}

/// EPIC-M1.138 — price-vs-target/SL chart with min/max axis labels and a
/// tap-to-inspect readout (UX rule: "charts must have readable axes/
/// tooltips and never be the sole source of numeric truth" — the exact
/// target/SL/current-price numbers are always shown as text alongside
/// this chart, never only in the drawing).
class PriceTargetChart extends StatefulWidget {
  final List<PricePoint> points;
  final double targetPrice;
  final double stopLoss;
  final double height;

  const PriceTargetChart({
    super.key,
    required this.points,
    required this.targetPrice,
    required this.stopLoss,
    this.height = 180,
  });

  @override
  State<PriceTargetChart> createState() => _PriceTargetChartState();
}

class _PriceTargetChartState extends State<PriceTargetChart> {
  int? _selectedIndex;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = MraColorScheme.of(context);

    if (widget.points.isEmpty) {
      return SizedBox(
        height: widget.height,
        child: Center(
          child: Text('No price history yet', style: theme.textTheme.bodySmall),
        ),
      );
    }

    final prices = widget.points.map((p) => p.price).toList()
      ..addAll([widget.targetPrice, widget.stopLoss]);
    final minPrice = prices.reduce((a, b) => a < b ? a : b);
    final maxPrice = prices.reduce((a, b) => a > b ? a : b);

    final selected = _selectedIndex == null
        ? widget.points.last
        : widget.points[_selectedIndex!];

    return Semantics(
      label: 'Price history versus target and stop-loss',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                maxPrice.toStringAsFixed(2),
                style: MraTypography.numeric(theme.textTheme.labelSmall!),
              ),
              _Legend(scheme: scheme),
            ],
          ),
          SizedBox(
            height: widget.height,
            child: GestureDetector(
              onTapDown: (details) => _selectNearest(details.localPosition),
              onPanUpdate: (details) => _selectNearest(details.localPosition),
              child: CustomPaint(
                size: Size.infinite,
                painter: _ChartPainter(
                  points: widget.points,
                  targetPrice: widget.targetPrice,
                  stopLoss: widget.stopLoss,
                  minPrice: minPrice,
                  maxPrice: maxPrice,
                  lineColor: theme.colorScheme.primary,
                  targetColor: scheme.positive,
                  stopLossColor: scheme.error,
                  selectedIndex: _selectedIndex,
                ),
              ),
            ),
          ),
          Text(
            minPrice.toStringAsFixed(2),
            style: MraTypography.numeric(theme.textTheme.labelSmall!),
          ),
          const SizedBox(height: MraSpacing.xs),
          Text(
            '${_dateLabel(selected.timestamp)} · ₹${selected.price.toStringAsFixed(2)}',
            style: theme.textTheme.labelMedium,
          ),
        ],
      ),
    );
  }

  void _selectNearest(Offset localPosition) {
    final width = context.size?.width ?? 1;
    final chartWidth = width <= 0 ? 1 : width;
    final fraction = (localPosition.dx / chartWidth).clamp(0.0, 1.0);
    final index = (fraction * (widget.points.length - 1)).round();
    setState(() => _selectedIndex = index);
  }

  static String _dateLabel(DateTime t) =>
      '${t.year}-${t.month.toString().padLeft(2, '0')}-${t.day.toString().padLeft(2, '0')}';
}

class _Legend extends StatelessWidget {
  final MraColorScheme scheme;
  const _Legend({required this.scheme});

  @override
  Widget build(BuildContext context) {
    final style = Theme.of(context).textTheme.labelSmall;
    Widget dot(Color color) => Container(
      width: 8,
      height: 8,
      margin: const EdgeInsets.only(right: 4),
      decoration: BoxDecoration(color: color, shape: BoxShape.circle),
    );
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        dot(scheme.positive),
        Text('Target', style: style),
        const SizedBox(width: MraSpacing.sm),
        dot(scheme.error),
        Text('Stop loss', style: style),
      ],
    );
  }
}

class _ChartPainter extends CustomPainter {
  final List<PricePoint> points;
  final double targetPrice;
  final double stopLoss;
  final double minPrice;
  final double maxPrice;
  final Color lineColor;
  final Color targetColor;
  final Color stopLossColor;
  final int? selectedIndex;

  _ChartPainter({
    required this.points,
    required this.targetPrice,
    required this.stopLoss,
    required this.minPrice,
    required this.maxPrice,
    required this.lineColor,
    required this.targetColor,
    required this.stopLossColor,
    required this.selectedIndex,
  });

  double _y(double price, Size size) {
    final range = (maxPrice - minPrice).abs() < 1e-9
        ? 1.0
        : (maxPrice - minPrice);
    return size.height - ((price - minPrice) / range) * size.height;
  }

  void _drawDashedLine(Canvas canvas, Size size, double y, Paint paint) {
    const dashWidth = 6.0;
    const gap = 4.0;
    var x = 0.0;
    while (x < size.width) {
      canvas.drawLine(Offset(x, y), Offset(x + dashWidth, y), paint);
      x += dashWidth + gap;
    }
  }

  @override
  void paint(Canvas canvas, Size size) {
    final targetPaint = Paint()
      ..color = targetColor
      ..strokeWidth = 1.5;
    final stopLossPaint = Paint()
      ..color = stopLossColor
      ..strokeWidth = 1.5;
    _drawDashedLine(canvas, size, _y(targetPrice, size), targetPaint);
    _drawDashedLine(canvas, size, _y(stopLoss, size), stopLossPaint);

    if (points.length >= 2) {
      final path = Path();
      for (var i = 0; i < points.length; i++) {
        final x = size.width * i / (points.length - 1);
        final y = _y(points[i].price, size);
        if (i == 0) {
          path.moveTo(x, y);
        } else {
          path.lineTo(x, y);
        }
      }
      canvas.drawPath(
        path,
        Paint()
          ..color = lineColor
          ..style = PaintingStyle.stroke
          ..strokeWidth = 2
          ..strokeCap = StrokeCap.round
          ..strokeJoin = StrokeJoin.round,
      );
    }

    if (selectedIndex != null && selectedIndex! < points.length) {
      final x = points.length == 1
          ? 0.0
          : size.width * selectedIndex! / (points.length - 1);
      final y = _y(points[selectedIndex!].price, size);
      canvas.drawLine(
        Offset(x, 0),
        Offset(x, size.height),
        Paint()
          ..color = lineColor.withValues(alpha: 0.3)
          ..strokeWidth = 1,
      );
      canvas.drawCircle(Offset(x, y), 4, Paint()..color = lineColor);
    }
  }

  @override
  bool shouldRepaint(covariant _ChartPainter oldDelegate) =>
      oldDelegate.points != points ||
      oldDelegate.selectedIndex != selectedIndex;
}
