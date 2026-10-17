import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:open_filex/open_filex.dart';
import 'package:path_provider/path_provider.dart';

import '../../core/format.dart';
import '../../data/models.dart';
import '../../widgets/async_view.dart';

class ReceiptScreen extends StatelessWidget {
  final Order order;
  const ReceiptScreen({super.key, required this.order});

  Future<void> _openPdf(BuildContext context) async {
    final b64 = order.pdfBase64;
    if (b64 == null) {
      showSuccess(context, 'The PDF receipt is not available yet.');
      return;
    }
    try {
      final dir = await getApplicationDocumentsDirectory();
      final file = File('${dir.path}/receipt_${order.orderId}.pdf');
      await file.writeAsBytes(base64Decode(b64));
      final result = await OpenFilex.open(file.path);
      if (result.type != ResultType.done && context.mounted) {
        showSuccess(context, 'Receipt saved. Install a PDF viewer to open it.');
      }
    } catch (e) {
      if (context.mounted) showError(context, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Receipt')),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        const Icon(Icons.check_circle, size: 72, color: Colors.green, semanticLabel: 'Success'),
        const SizedBox(height: 8),
        Text('Payment successful', textAlign: TextAlign.center, style: Theme.of(context).textTheme.headlineSmall),
        const SizedBox(height: 8),
        SelectableText('Order ${order.orderId}', textAlign: TextAlign.center),
        const SectionHeader('Items'),
        for (final i in order.items)
          ListTile(
            title: Text('${i['variant_id']}'),
            subtitle: Text('Qty ${i['quantity']}'),
            trailing: Text(formatMoney((i['unit_price_minor'] as int) * (i['quantity'] as int), currency: order.currency)),
          ),
        const Divider(),
        ListTile(title: const Text('Subtotal'), trailing: Text(formatMoney(order.subtotalMinor, currency: order.currency))),
        if (order.discountMinor > 0)
          ListTile(title: const Text('Discount'), trailing: Text('− ${formatMoney(order.discountMinor, currency: order.currency)}')),
        ListTile(
          title: const Text('Total paid', style: TextStyle(fontWeight: FontWeight.bold)),
          trailing: Text(formatMoney(order.totalMinor, currency: order.currency), style: const TextStyle(fontWeight: FontWeight.bold)),
        ),
        const SizedBox(height: 24),
        FilledButton.icon(
          onPressed: () => _openPdf(context),
          icon: const Icon(Icons.picture_as_pdf),
          label: const Text('Open PDF receipt'),
        ),
        const SizedBox(height: 12),
        OutlinedButton(onPressed: () => context.go('/store'), child: const Text('Back to store')),
      ]),
    );
  }
}
