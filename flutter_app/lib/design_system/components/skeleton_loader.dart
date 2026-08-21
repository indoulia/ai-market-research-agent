import 'package:flutter/material.dart';

import '../tokens/mra_spacing.dart';
import '../util/reduce_motion.dart';

/// EPIC-M1.133 — shimmering skeleton block used instead of layout-jumping
/// spinners while content loads. Shimmer is skipped under reduced motion,
/// leaving a static placeholder block.
class SkeletonBox extends StatefulWidget {
  final double width;
  final double height;
  final double borderRadius;

  const SkeletonBox({
    super.key,
    this.width = double.infinity,
    this.height = 16,
    this.borderRadius = MraRadiiForSkeleton.value,
  });

  @override
  State<SkeletonBox> createState() => _SkeletonBoxState();
}

class MraRadiiForSkeleton {
  static const double value = 8;
}

class _SkeletonBoxState extends State<SkeletonBox>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1100),
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final base = Theme.of(context).colorScheme.surfaceContainerHigh;
    final highlight = Theme.of(context).colorScheme.surfaceContainerHighest;
    final reduceMotion = mraReduceMotion(context);

    final shape = BoxDecoration(
      color: base,
      borderRadius: BorderRadius.circular(widget.borderRadius),
    );

    if (reduceMotion) {
      return Container(
        width: widget.width,
        height: widget.height,
        decoration: shape,
      );
    }

    return AnimatedBuilder(
      animation: _controller,
      builder: (context, _) {
        return Container(
          width: widget.width,
          height: widget.height,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(widget.borderRadius),
            gradient: LinearGradient(
              begin: Alignment(-1 + _controller.value * 2, 0),
              end: Alignment(1 + _controller.value * 2, 0),
              colors: [base, highlight, base],
              stops: const [0.35, 0.5, 0.65],
            ),
          ),
        );
      },
    );
  }
}

/// EPIC-M1.133 — skeleton shape matching a recommendation/KPI card so
/// loading states never jump layout when real content arrives.
class SkeletonCard extends StatelessWidget {
  const SkeletonCard({super.key});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(MraSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: const [
          SkeletonBox(width: 120, height: 14),
          SizedBox(height: MraSpacing.sm),
          SkeletonBox(height: 24),
          SizedBox(height: MraSpacing.sm),
          SkeletonBox(width: 180, height: 14),
        ],
      ),
    );
  }
}
