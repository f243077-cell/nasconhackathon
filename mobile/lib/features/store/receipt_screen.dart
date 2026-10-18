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
import '../../widgets/sync_status_bar.dart';
import '../../widgets/ui.dart';

class ReceiptScreen extends ConsumerStatefulWidget {
  final Order order;
  const ReceiptScreen({super.key, required this.order});

  @override
  ConsumerState<ReceiptScreen> createState() => _ReceiptScreenState();
}

class _ReceiptScreenState extends ConsumerState<ReceiptScreen> {
  final _placedAt = DateTime.now();
  bool _opening = false;

  /// Uses the PDF from the checkout response, else downloads it from the server.
  Future<void> _openPdf() async {
    final order = widget.order;
    setState(() => _opening = true);
    try {
      final b64 = order.pdfBase64;
      final bytes = b64 != null ? base64Decode(b64) : await ref.read(repositoryProvider).receiptPdf(order.orderId);
      final dir = await getApplicationDocumentsDirectory();
      final file = File('${dir.path}/receipt_${order.orderId}.pdf');
      await file.writeAsBytes(bytes);
      final result = await OpenFilex.open(file.path);
      if (result.type != ResultType.done && mounted) {
        showSuccess(context, 'Receipt saved. Install a PDF viewer to open it.');
      }
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _opening = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final order = widget.order;
    final p = context.palette;
    String money(int v) => formatMoney(v, currency: order.currency);
    // Order items only carry variant ids: look the names up in the (cached) catalogue.
    final products = ref.watch(productsProvider).value ?? const <Product>[];
    (Product, Variant)? lookup(String id) {
      for (final pr in products) {
        for (final v in pr.variants) {
          if (v.variantId == id) return (pr, v);
        }
      }
      return null;
    }

    return Scaffold(
      bottomNavigationBar: BottomActionBar(children: [
        PrimaryButton(label: 'Download receipt (PDF)', icon: Icons.download_rounded, loading: _opening, onPressed: _openPdf),
        SecondaryButton(label: 'Back to store', onPressed: () => context.go('/store')),
      ]),
      body: SafeArea(
        bottom: false,
        child: ListView(padding: const EdgeInsets.fromLTRB(20, 4, 20, 24), children: [
          ScreenHeader(
            leading: Semantics(
              button: true,
              label: 'Close',
              excludeSemantics: true,
              child: GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: () => context.go('/store'),
                child: SizedBox(
                  height: 48,
                  child: Row(children: [
                    Icon(Icons.close_rounded, size: 18, color: p.label2),
                    const SizedBox(width: 6),
                    Text('CLOSE', style: condensed(14, weight: FontWeight.w600, tracking: 1, color: p.label2)),
                  ]),
                ),
              ),
            ),
            trailing: const StatusPill(),
          ),
          const SizedBox(height: 10),
          Center(
            child: Container(
              width: 72,
              height: 72,
              decoration: BoxDecoration(color: p.accent, shape: BoxShape.circle),
              child: Icon(Icons.check_rounded, size: 40, color: p.onAccent, semanticLabel: 'Success'),
            ),
          ),
          const SizedBox(height: 12),
          Semantics(
            header: true,
            child: Text('PAYMENT SUCCESSFUL', textAlign: TextAlign.center, style: condensed(36, weight: FontWeight.w800, color: p.label, height: 1)),
          ),
          const SizedBox(height: 8),
          SelectableText(
            'Order ${order.orderId} · ${formatStamp(_placedAt)}',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 14, color: p.label3),
          ),
          const SizedBox(height: 22),
          _OrderTracker(status: order.status),
          const SizedBox(height: 22),
          Panel(
            child: Column(children: [
              for (final i in order.items)
                Builder(builder: (context) {
                  final found = lookup('${i['variant_id']}');
                  final qty = i['quantity'] as int;
                  return Container(
                    padding: const EdgeInsets.only(bottom: 12),
                    margin: const EdgeInsets.only(bottom: 12),
                    decoration: BoxDecoration(border: Border(bottom: BorderSide(color: p.border))),
                    child: Row(children: [
                      ClipRRect(
                        borderRadius: BorderRadius.circular(8),
                        child: SizedBox.square(
                          dimension: 48,
                          child: ProductArtwork(type: found?.$1.type ?? 'apparel', imageUrl: found?.$1.imageUrl, iconSize: 22),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Text(found?.$1.name ?? '${i['variant_id']}', style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600, color: p.label)),
                          Text(
                            [if (found != null && found.$2.label.isNotEmpty) found.$2.label.replaceAll(' / ', ' · '), '×$qty'].join(' · '),
                            style: TextStyle(fontSize: 13, color: p.label3),
                          ),
                        ]),
                      ),
                      Text(money((i['unit_price_minor'] as int) * qty), style: TextStyle(fontSize: 15, color: p.label)),
                    ]),
                  );
                }),
              ValueRow('Subtotal', money(order.subtotalMinor)),
              if (order.discountMinor > 0) ValueRow('Discount', '− ${money(order.discountMinor)}', valueColor: p.accent),
              const ValueRow('Paid with', 'Test card'),
              const SizedBox(height: 6),
              ValueRow('Total', money(order.totalMinor), emphasized: true),
            ]),
          ),
        ]),
      ),
    );
  }
}

/// Paid → Packed → Shipped → Delivered, lit up to the order's status.
class _OrderTracker extends StatelessWidget {
  final String status;
  const _OrderTracker({required this.status});

  static const _steps = ['Paid', 'Packed', 'Shipped', 'Delivered'];

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    final reached = switch (status.toLowerCase()) {
      'delivered' => 3,
      'shipped' => 2,
      'packed' || 'fulfilled' => 1,
      _ => 0,
    };
    return Semantics(
      label: 'Order status: ${_steps[reached]}',
      excludeSemantics: true,
      child: LayoutBuilder(builder: (context, c) {
        final step = c.maxWidth / 4;
        return Stack(children: [
          Positioned(left: step / 2, right: step / 2, top: 7, child: Container(height: 2, color: p.raised)),
          Positioned(left: step / 2, top: 7, child: Container(height: 2, width: step * reached, color: p.accent)),
          Row(children: [
            for (var i = 0; i < 4; i++)
              Expanded(
                child: Column(children: [
                  Container(
                    width: 16,
                    height: 16,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: i <= reached ? p.accent : p.canvas,
                      border: i <= reached ? null : Border.all(color: p.border, width: 2),
                    ),
                  ),
                  const SizedBox(height: 6),
                  Text(_steps[i].toUpperCase(), style: condensed(12, weight: FontWeight.w600, tracking: 1, color: i <= reached ? p.accent : p.muted)),
                ]),
              ),
          ]),
        ]);
      }),
    );
  }
}
