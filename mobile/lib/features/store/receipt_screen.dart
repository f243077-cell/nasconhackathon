import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:open_filex/open_filex.dart';
import 'package:path_provider/path_provider.dart';

import '../../core/format.dart';
import '../../core/theme.dart';
import '../../data/models.dart';
import '../../data/repository.dart';
import '../../widgets/async_view.dart';
import '../../widgets/ui.dart';

class ReceiptScreen extends ConsumerWidget {
  final Order order;
  const ReceiptScreen({super.key, required this.order});

  /// Uses the PDF from the checkout response, else downloads it from the server.
  Future<void> _openPdf(BuildContext context, WidgetRef ref) async {
    try {
      final b64 = order.pdfBase64;
      final bytes = b64 != null ? base64Decode(b64) : await ref.read(repositoryProvider).receiptPdf(order.orderId);
      final dir = await getApplicationDocumentsDirectory();
      final file = File('${dir.path}/receipt_${order.orderId}.pdf');
      await file.writeAsBytes(bytes);
      final result = await OpenFilex.open(file.path);
      if (result.type != ResultType.done && context.mounted) {
        showSuccess(context, 'Receipt saved. Install a PDF viewer to open it.');
      }
    } catch (e) {
      if (context.mounted) showError(context, e);
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = Theme.of(context).textTheme;
    final p = context.palette;
    String money(int v) => formatMoney(v, currency: order.currency);
    return Scaffold(
      appBar: AppBar(title: const Text('Receipt'), automaticallyImplyLeading: false, actions: [
        TextButton(onPressed: () => context.go('/store'), child: const Text('Done', style: TextStyle(fontWeight: FontWeight.w600))),
      ]),
      bottomNavigationBar: BottomActionBar(children: [
        PrimaryButton(label: 'Open PDF Receipt', icon: Icons.description_rounded, onPressed: () => _openPdf(context, ref)),
      ]),
      body: ListView(padding: const EdgeInsets.only(bottom: 24), children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(32, 24, 32, 28),
          child: Column(children: [
            Icon(Icons.check_circle_rounded, size: 64, color: p.success, semanticLabel: 'Success'),
            const SizedBox(height: 14),
            Text('Payment Complete', style: t.headlineMedium, textAlign: TextAlign.center),
            const SizedBox(height: 6),
            Text(money(order.totalMinor), style: t.titleLarge!.copyWith(fontFeatures: tabular)),
            const SizedBox(height: 6),
            SelectableText(order.orderId, style: t.bodySmall, textAlign: TextAlign.center),
          ]),
        ),
        Section(header: 'Items', children: [
          for (final i in order.items)
            ValueRow(
              '${i['variant_id']}  ×${i['quantity']}',
              money((i['unit_price_minor'] as int) * (i['quantity'] as int)),
            ),
        ]),
        Section(children: [
          ValueRow('Subtotal', money(order.subtotalMinor)),
          if (order.discountMinor > 0) ValueRow('Discount', '−${money(order.discountMinor)}'),
          ValueRow('Total Paid', money(order.totalMinor), emphasized: true),
        ]),
      ]),
    );
  }
}
