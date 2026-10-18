import 'package:flutter/material.dart';

import '../core/theme.dart';
import 'ui.dart';

/// Confirmation before risky actions (checkout, release, transfer, loan, correction, sign out).
/// Cancel on the leading side, the action named by its result.
Future<bool> confirmAction(
  BuildContext context, {
  required String title,
  required String message,
  String confirmLabel = 'Confirm',
  bool destructive = false,
  Widget? extra,
}) async {
  final result = await showDialog<bool>(
    context: context,
    barrierDismissible: true,
    builder: (ctx) => ConfirmDialog(
      title: title,
      message: message,
      confirmLabel: confirmLabel,
      destructive: destructive,
      extra: extra,
    ),
  );
  return result ?? false;
}

class ConfirmDialog extends StatelessWidget {
  final String title;
  final String message;
  final String confirmLabel;
  final bool destructive;
  final Widget? extra;
  const ConfirmDialog({super.key, required this.title, required this.message, required this.confirmLabel, this.destructive = false, this.extra});

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    return Dialog(
      insetPadding: const EdgeInsets.symmetric(horizontal: 24),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 22, 20, 18),
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Text(title.toUpperCase(), style: condensed(26, weight: FontWeight.w800, color: p.label, height: 1.05)),
          const SizedBox(height: 10),
          Text(message, style: TextStyle(fontSize: 15, color: p.label2, height: 1.4)),
          if (extra != null) ...[const SizedBox(height: 14), extra!],
          const SizedBox(height: 20),
          Row(children: [
            Expanded(child: SecondaryButton(label: 'Cancel', height: 48, onPressed: () => Navigator.pop(context, false))),
            const SizedBox(width: 10),
            Expanded(
              child: destructive
                  ? SecondaryButton(label: confirmLabel, height: 48, destructive: true, onPressed: () => Navigator.pop(context, true))
                  : PrimaryButton(label: confirmLabel, height: 48, onPressed: () => Navigator.pop(context, true)),
            ),
          ]),
        ]),
      ),
    );
  }
}
