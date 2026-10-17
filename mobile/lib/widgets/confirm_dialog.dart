import 'package:flutter/cupertino.dart';

/// Confirmation before risky actions (checkout, release, transfer, loan, compensation, sign out).
/// alerts.md › Buttons: Cancel on the leading side, the action named by its result.
Future<bool> confirmAction(
  BuildContext context, {
  required String title,
  required String message,
  String confirmLabel = 'Confirm',
  bool destructive = false,
}) async {
  final result = await showCupertinoDialog<bool>(
    context: context,
    barrierDismissible: true,
    builder: (ctx) => CupertinoAlertDialog(
      title: Text(title),
      content: Padding(padding: const EdgeInsets.only(top: 4), child: Text(message)),
      actions: [
        CupertinoDialogAction(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
        CupertinoDialogAction(
          isDefaultAction: !destructive,
          isDestructiveAction: destructive,
          onPressed: () => Navigator.pop(ctx, true),
          child: Text(confirmLabel),
        ),
      ],
    ),
  );
  return result ?? false;
}
