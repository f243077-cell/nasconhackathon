import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:uuid/uuid.dart';

import '../../core/format.dart';
import '../../core/session.dart';
import '../../core/theme.dart';
import '../../data/repository.dart';
import '../../data/sync_queue.dart';
import '../../widgets/async_view.dart';
import '../../widgets/confirm_dialog.dart';
import '../../widgets/ui.dart';
import 'cart.dart';

/// Cart, discount, mock payment and checkout (with confirmation). Pay sits in the bottom bar.
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
    'tok_success': 'Approves',
    'tok_declined': 'Declines',
    'tok_capture_fail': 'Fails',
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
        _codeError = "That code isn't valid.";
      }
    });
  }

  Future<void> _pay(int totalMinor) async {
    final ok = await confirmAction(
      context,
      title: 'Pay ${formatMoney(totalMinor)}?',
      message: 'Your order will be placed and the test card charged.',
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
    final t = Theme.of(context).textTheme;
    final p = context.palette;

    if (lines.isEmpty) {
      return Scaffold(
        appBar: AppBar(title: const Text('Cart')),
        body: EmptyState(
          message: 'Your cart is empty',
          icon: Icons.shopping_cart_rounded,
          action: TextButton(onPressed: () => context.go('/store'), child: const Text('Browse the Store')),
        ),
      );
    }

    return Scaffold(
      appBar: AppBar(title: const Text('Cart')),
      bottomNavigationBar: BottomActionBar(children: [
        if (offline)
          Row(mainAxisAlignment: MainAxisAlignment.center, children: [
            Icon(Icons.cloud_off_rounded, size: 16, color: p.warning),
            const SizedBox(width: 6),
            Flexible(child: Text('Checkout needs an internet connection.', style: t.bodyMedium)),
          ]),
        PrimaryButton(label: 'Pay ${formatMoney(total)}', loading: _paying, onPressed: offline ? null : () => _pay(total)),
      ]),
      body: ListView(padding: const EdgeInsets.only(top: 12, bottom: 24), children: [
        Section(
          dividerIndent: 84,
          children: [
            for (final l in lines)
              Padding(
                padding: const EdgeInsets.fromLTRB(12, 12, 4, 12),
                child: Row(children: [
                  ClipRRect(
                    borderRadius: BorderRadius.circular(10),
                    child: SizedBox.square(dimension: 56, child: ProductArtwork(type: l.product.type, iconSize: 26)),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text(l.product.name, style: t.titleMedium, overflow: TextOverflow.ellipsis),
                      if (l.variant.label.isNotEmpty) Text(l.variant.label, style: t.bodyMedium),
                      const SizedBox(height: 8),
                      Row(children: [
                        QuantityStepper(
                          value: l.quantity,
                          max: l.variant.stock.clamp(1, 10),
                          onChanged: (q) => ref.read(cartProvider.notifier).setQuantity(l.variant.variantId, q),
                        ),
                        const Spacer(),
                        Text(formatMoney(l.totalMinor), style: t.bodyLarge!.copyWith(fontFeatures: tabular)),
                      ]),
                    ]),
                  ),
                  IconButton(
                    tooltip: 'Remove ${l.product.name}',
                    icon: Icon(Icons.close_rounded, color: p.secondaryLabel),
                    onPressed: () => ref.read(cartProvider.notifier).remove(l.variant.variantId),
                  ),
                ]),
              ),
          ],
        ),
        Section(
          header: 'Discount Code',
          footer: _codeError ?? (_appliedCode != null ? '$_appliedCode applied, 10% off.' : null),
          children: [
            Row(children: [
              Expanded(
                child: TextField(
                  controller: _code,
                  textCapitalization: TextCapitalization.characters,
                  autocorrect: false,
                  onSubmitted: (_) => _applyCode(),
                  decoration: const InputDecoration(
                    hintText: 'Enter code',
                    filled: false,
                    border: InputBorder.none,
                    enabledBorder: InputBorder.none,
                    focusedBorder: InputBorder.none,
                  ),
                ),
              ),
              TextButton(onPressed: _applyCode, child: const Text('Apply')),
            ]),
          ],
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(32, 0, 32, 8),
          child: Text('Test Card', style: t.bodySmall!.copyWith(fontWeight: FontWeight.w600)),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 28),
          child: Segmented<String>(value: _token, options: _tokens, onChanged: (v) => setState(() => _token = v)),
        ),
        Section(children: [
          ValueRow('Subtotal', formatMoney(subtotal)),
          if (discount > 0) ValueRow('Discount', '−${formatMoney(discount)}'),
          ValueRow('Total', formatMoney(total), emphasized: true),
        ]),
      ]),
    );
  }
}
