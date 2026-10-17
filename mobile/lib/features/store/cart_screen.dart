import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:uuid/uuid.dart';

import '../../core/format.dart';
import '../../core/session.dart';
import '../../data/repository.dart';
import '../../data/sync_queue.dart';
import '../../widgets/async_view.dart';
import '../../widgets/confirm_dialog.dart';
import 'cart.dart';
import 'product_screen.dart';

/// Cart + discount + mock payment + checkout (with confirmation).
class CartScreen extends ConsumerStatefulWidget {
  const CartScreen({super.key});

  @override
  ConsumerState<CartScreen> createState() => _CartScreenState();
}

class _CartScreenState extends ConsumerState<CartScreen> {
  final _code = TextEditingController();
  String? _appliedCode;
  String? _codeError;
  String _token = 'tok_success';
  bool _paying = false;

  static const _tokens = {
    'tok_success': 'Test card (approves)',
    'tok_declined': 'Test card (declined)',
    'tok_capture_fail': 'Test card (capture fails)',
  };

  @override
  void dispose() {
    _code.dispose();
    super.dispose();
  }

  void _applyCode() {
    final code = _code.text.trim().toUpperCase();
    setState(() {
      if (code.isEmpty) {
        _appliedCode = null;
        _codeError = null;
      } else if (code == 'WELCOME10') {
        _appliedCode = code;
        _codeError = null;
      } else {
        _appliedCode = null;
        _codeError = "That discount code isn't valid.";
      }
    });
  }

  Future<void> _pay(int totalMinor) async {
    final ok = await confirmAction(
      context,
      title: 'Confirm payment',
      message: 'Pay ${formatMoney(totalMinor)} now?',
      confirmLabel: 'Pay',
    );
    if (!ok || !mounted) return;
    setState(() => _paying = true);
    final session = ref.read(sessionProvider)!;
    final lines = ref.read(cartProvider);
    try {
      final order = await ref.read(repositoryProvider).checkout({
        'order_id': 'ord-${const Uuid().v4()}',
        'customer_id': session.user.id,
        'items': [for (final l in lines) {'variant_id': l.variant.variantId, 'quantity': l.quantity}],
        'discount_code': _appliedCode,
        'payment': {'token': _token},
      });
      ref.read(cartProvider.notifier).clear();
      ref.invalidate(productsProvider); // stock changed
      if (mounted) context.pushReplacement('/receipt', extra: order);
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _paying = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final lines = ref.watch(cartProvider);
    final offline = ref.watch(syncProvider).isOffline;
    final subtotal = lines.fold<int>(0, (s, l) => s + l.totalMinor);
    final discount = _appliedCode == 'WELCOME10' ? subtotal * 10 ~/ 100 : 0;
    final total = subtotal - discount;

    return Scaffold(
      appBar: AppBar(title: const Text('Cart')),
      body: lines.isEmpty
          ? Column(mainAxisAlignment: MainAxisAlignment.center, children: [
              const EmptyState(message: 'Your cart is empty', icon: Icons.shopping_cart_outlined),
              FilledButton(onPressed: () => context.go('/store'), child: const Text('Browse the store')),
            ])
          : ListView(padding: const EdgeInsets.all(16), children: [
              for (final l in lines)
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(8),
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      ListTile(
                        contentPadding: EdgeInsets.zero,
                        title: Text(l.product.name),
                        subtitle: Text('${l.variant.label} · ${formatMoney(l.variant.priceMinor)} each'),
                        trailing: IconButton(
                          tooltip: 'Remove ${l.product.name}',
                          icon: const Icon(Icons.delete_outline),
                          onPressed: () => ref.read(cartProvider.notifier).remove(l.variant.variantId),
                        ),
                      ),
                      QuantityStepper(
                        value: l.quantity,
                        max: l.variant.stock.clamp(1, 10),
                        onChanged: (q) => ref.read(cartProvider.notifier).setQuantity(l.variant.variantId, q),
                      ),
                    ]),
                  ),
                ),
              const SectionHeader('Discount code'),
              Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Expanded(
                  child: TextField(
                    controller: _code,
                    textCapitalization: TextCapitalization.characters,
                    decoration: InputDecoration(labelText: 'Code', errorText: _codeError),
                  ),
                ),
                const SizedBox(width: 8),
                OutlinedButton(onPressed: _applyCode, child: const Text('Apply')),
              ]),
              const SectionHeader('Payment method'),
              Wrap(spacing: 8, runSpacing: 8, children: [
                for (final t in _tokens.entries)
                  ChoiceChip(label: Text(t.value), selected: _token == t.key, onSelected: (_) => setState(() => _token = t.key)),
              ]),
              const SectionHeader('Summary'),
              _row('Subtotal', formatMoney(subtotal)),
              if (discount > 0) _row('Discount ($_appliedCode)', '− ${formatMoney(discount)}'),
              _row('Total', formatMoney(total), bold: true),
              const SizedBox(height: 24),
              if (offline)
                const Padding(
                  padding: EdgeInsets.only(bottom: 8),
                  child: Text('Checkout needs an internet connection.', textAlign: TextAlign.center),
                ),
              FilledButton(
                onPressed: _paying || offline ? null : () => _pay(total),
                child: _paying
                    ? const SizedBox(height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2))
                    : Text('Pay ${formatMoney(total)}'),
              ),
            ]),
    );
  }

  Widget _row(String label, String value, {bool bold = false}) {
    final style = bold ? Theme.of(context).textTheme.titleMedium : null;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(children: [Expanded(child: Text(label, style: style)), Text(value, style: style)]),
    );
  }
}
