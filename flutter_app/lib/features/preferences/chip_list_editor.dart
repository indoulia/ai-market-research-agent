import 'package:flutter/material.dart';

import '../../design_system/design_system.dart';

/// EPIC-M1.142 — add/remove editor for an open-ended string list
/// (watchlist symbols, sectors, industries). No enumeration endpoint
/// exists for sectors/industries, so free-text entry is the honest
/// choice over a fabricated fixed picklist.
class ChipListEditor extends StatefulWidget {
  final String label;
  final String hintText;
  final List<String> values;
  final ValueChanged<List<String>> onChanged;

  const ChipListEditor({
    super.key,
    required this.label,
    required this.hintText,
    required this.values,
    required this.onChanged,
  });

  @override
  State<ChipListEditor> createState() => _ChipListEditorState();
}

class _ChipListEditorState extends State<ChipListEditor> {
  final TextEditingController _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _add() {
    final value = _controller.text.trim().toUpperCase();
    if (value.isEmpty || widget.values.contains(value)) return;
    widget.onChanged([...widget.values, value]);
    _controller.clear();
  }

  void _remove(String value) {
    widget.onChanged(widget.values.where((v) => v != value).toList());
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(widget.label, style: theme.textTheme.labelLarge),
        const SizedBox(height: MraSpacing.xs),
        Row(
          children: [
            Expanded(
              child: TextField(
                controller: _controller,
                decoration: InputDecoration(
                  hintText: widget.hintText,
                  isDense: true,
                ),
                onSubmitted: (_) => _add(),
              ),
            ),
            const SizedBox(width: MraSpacing.sm),
            IconButton(icon: const Icon(Icons.add), onPressed: _add),
          ],
        ),
        if (widget.values.isNotEmpty) ...[
          const SizedBox(height: MraSpacing.sm),
          Wrap(
            spacing: MraSpacing.xs,
            runSpacing: MraSpacing.xs,
            children: widget.values
                .map((v) => Chip(label: Text(v), onDeleted: () => _remove(v)))
                .toList(),
          ),
        ],
      ],
    );
  }
}
