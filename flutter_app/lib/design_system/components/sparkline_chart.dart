import 'package:flutter/material.dart';

/// EPIC-M1.133 — minimal dependency-free sparkline used for compact price
/// history in cards. Not a full charting library by design: dense cards
/// only need a trend cue, not interactive chart chrome.
///
/// EPIC-M3.15 — optional interactive mode (`interactive: true` +
/// `pointLabels`) adds tap/hover point selection so a caller can show the
/// exact value at a point on demand (UI Scope: "compact charts with exact
/// values available on interaction"), without turning every existing
/// (non-interactive) sparkline in the app into something it isn't --
/// `interactive` defaults to `false`, so every pre-existing call site
/// (e.g. price-history cards) is unaffected.
class SparklineChart extends StatefulWidget {
  final List<double> values;
  final Color? color;
  final double height;
  final bool interactive;

  /// Pre-formatted label for each entry in [values] (same length), shown
  /// when that point is selected. Required when [interactive] is true.
  final List<String>? pointLabels;

  const SparklineChart({
    super.key,
    required this.values,
    this.color,
    this.height = 32,
    this.interactive = false,
    this.pointLabels,
  });

  @override
  State<SparklineChart> createState() => _SparklineChartState();
}

class _SparklineChartState extends State<SparklineChart> {
  int? _selectedIndex;

  void _selectFromLocalX(double localX, double width) {
    if (widget.values.length < 2 || width <= 0) return;
    final ratio = (localX / width).clamp(0.0, 1.0);
    final index = (ratio * (widget.values.length - 1)).round();
    if (index == _selectedIndex) return;
    setState(() => _selectedIndex = index);
  }

  @override
  Widget build(BuildContext context) {
    final resolvedColor = widget.color ?? Theme.of(context).colorScheme.primary;
    final chart = SizedBox(
      height: widget.height,
      width: double.infinity,
      child: CustomPaint(
        painter: _SparklinePainter(
          values: widget.values,
          color: resolvedColor,
          highlightIndex: widget.interactive ? _selectedIndex : null,
        ),
      ),
    );

    if (!widget.interactive || widget.values.length < 2) {
      return Semantics(label: 'Price trend sparkline', child: chart);
    }

    final labels = widget.pointLabels;
    final selectedLabel =
        (_selectedIndex != null &&
            labels != null &&
            _selectedIndex! < labels.length)
        ? labels[_selectedIndex!]
        : null;

    return Semantics(
      label: 'Trend chart, tap or drag to see the exact value at a point',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          SizedBox(
            height: 16,
            child: selectedLabel == null
                ? null
                : Text(
                    selectedLabel,
                    style: Theme.of(context).textTheme.labelSmall?.copyWith(
                      fontWeight: FontWeight.w600,
                    ),
                  ),
          ),
          LayoutBuilder(
            builder: (context, constraints) {
              return MouseRegion(
                onHover: (event) => _selectFromLocalX(
                  event.localPosition.dx,
                  constraints.maxWidth,
                ),
                onExit: (_) => setState(() => _selectedIndex = null),
                child: GestureDetector(
                  onTapDown: (details) => _selectFromLocalX(
                    details.localPosition.dx,
                    constraints.maxWidth,
                  ),
                  onPanUpdate: (details) => _selectFromLocalX(
                    details.localPosition.dx,
                    constraints.maxWidth,
                  ),
                  child: chart,
                ),
              );
            },
          ),
        ],
      ),
    );
  }
}

class _SparklinePainter extends CustomPainter {
  final List<double> values;
  final Color color;
  final int? highlightIndex;

  _SparklinePainter({
    required this.values,
    required this.color,
    this.highlightIndex,
  });

  @override
  void paint(Canvas canvas, Size size) {
    if (values.length < 2) return;

    final minV = values.reduce((a, b) => a < b ? a : b);
    final maxV = values.reduce((a, b) => a > b ? a : b);
    final range = (maxV - minV).abs() < 1e-9 ? 1.0 : (maxV - minV);

    Offset pointAt(int i) {
      final x = size.width * i / (values.length - 1);
      final normalized = (values[i] - minV) / range;
      final y = size.height - (normalized * size.height);
      return Offset(x, y);
    }

    final path = Path();
    for (var i = 0; i < values.length; i++) {
      final point = pointAt(i);
      if (i == 0) {
        path.moveTo(point.dx, point.dy);
      } else {
        path.lineTo(point.dx, point.dy);
      }
    }

    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;

    canvas.drawPath(path, paint);

    final index = highlightIndex;
    if (index != null && index >= 0 && index < values.length) {
      final point = pointAt(index);
      canvas.drawCircle(point, 4, Paint()..color = color);
      canvas.drawCircle(
        point,
        4,
        Paint()
          ..color = Colors.white
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.5,
      );
    }
  }

  @override
  bool shouldRepaint(covariant _SparklinePainter oldDelegate) {
    return oldDelegate.values != values ||
        oldDelegate.color != color ||
        oldDelegate.highlightIndex != highlightIndex;
  }
}
