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

/// Checkout: items, discount code, totals, mock payment method. Pay sits at the bottom.
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

  // Mock gateway tokens (CLAUDE.md §7.9): each test card triggers one outcome.
  static const _tokens = {
    'tok_success': ('Test card', 'Approves'),
    'tok_declined': ('Test card', 'Declines'),
    'tok_capture_fail': ('Test card', 'Capture fails'),
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
    final p = context.palette;

    if (lines.isEmpty) {
      return FlatPage(
        title: 'Checkout',
        backFallback: '/store',
        children: [
          EmptyState(
            message: 'Your cart is empty',
            icon: Icons.shopping_bag_outlined,
            action: SecondaryButton(label: 'Browse the store', onPressed: () => context.go('/store')),
          ),
        ],
      );
    }

    return FlatPage(
      title: 'Checkout',
      backFallback: '/store',
      actions: [
        PrimaryButton(label: 'Pay ${formatMoney(total)}', loading: _paying, onPressed: offline ? null : () => _pay(total)),
      ],
      children: [
        if (offline) ...[
          _Banner(icon: Icons.cloud_off_rounded, text: 'Checkout needs an internet connection.'),
          const SizedBox(height: 14),
        ],
        for (final l in lines)
          Container(
            padding: const EdgeInsets.only(bottom: 14),
            margin: const EdgeInsets.only(bottom: 14),
            decoration: BoxDecoration(border: Border(bottom: BorderSide(color: p.raised))),
            child: Row(children: [
              ClipRRect(
                borderRadius: BorderRadius.circular(10),
                child: SizedBox.square(dimension: 60, child: ProductArtwork(type: l.product.type, imageUrl: l.product.imageUrl, iconSize: 26)),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(l.product.name, maxLines: 2, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600, color: p.label)),
                  Text(
                    [if (l.variant.label.isNotEmpty) l.variant.label.replaceAll(' / ', ' · '), formatMoney(l.totalMinor)].join(' · '),
                    style: TextStyle(fontSize: 13, color: p.label3),
                  ),
                ]),
              ),
              const SizedBox(width: 8),
              // Down to zero removes the line.
              QuantityStepper(
                value: l.quantity,
                min: 0,
                max: l.variant.stock.clamp(1, 10),
                onChanged: (q) => q == 0
                    ? ref.read(cartProvider.notifier).remove(l.variant.variantId)
                    : ref.read(cartProvider.notifier).setQuantity(l.variant.variantId, q),
              ),
            ]),
          ),
        TextField(
          controller: _code,
          textCapitalization: TextCapitalization.characters,
          autocorrect: false,
          onSubmitted: (_) => _applyCode(),
          onChanged: (_) {
            if (_appliedCode != null || _codeError != null) setState(() => _codeError = null);
          },
          style: condensed(16, weight: FontWeight.w700, tracking: 1.5, color: p.label),
          decoration: InputDecoration(
            hintText: 'Discount code',
            errorText: _codeError,
            suffixIcon: _appliedCode != null && _code.text.trim().toUpperCase() == _appliedCode
                ? Padding(
                    padding: const EdgeInsets.only(right: 14),
                    child: Row(mainAxisSize: MainAxisSize.min, children: [
                      Text('✓ Code applied', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: p.accent)),
                    ]),
                  )
                : TextButton(onPressed: _applyCode, child: const Text('APPLY')),
          ),
        ),
        const SizedBox(height: 16),
        ValueRow('Subtotal', formatMoney(subtotal)),
        if (discount > 0) ValueRow('Discount (10%)', '− ${formatMoney(discount)}', valueColor: p.accent),
        const SizedBox(height: 6),
        ValueRow('Total', formatMoney(total), emphasized: true),
        const SizedBox(height: 18),
        const SectionLabel('Pay with'),
        RadioGroup<String>(
          groupValue: _token,
          onChanged: (v) => setState(() => _token = v ?? _token),
          child: Column(children: [
            for (final e in _tokens.entries) ...[
              _PayOption(value: e.key, title: e.value.$1, detail: e.value.$2, selected: e.key == _token, onTap: () => setState(() => _token = e.key)),
              const SizedBox(height: 8),
            ],
          ]),
        ),
        Text('Demo payment — no real money is charged.', style: TextStyle(fontSize: 12, color: p.label3)),
      ],
    );
  }
}

class _PayOption extends StatelessWidget {
  final String value;
  final String title;
  final String detail;
  final bool selected;
  final VoidCallback onTap;
  const _PayOption({required this.value, required this.title, required this.detail, required this.selected, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    return Material(
      color: Colors.transparent,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: selected ? p.accent : p.border, width: selected ? 2 : 1),
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: onTap,
        child: SizedBox(
          height: 52,
          child: Row(children: [
            Radio<String>(value: value, activeColor: p.accent),
            Expanded(child: Text(title, style: TextStyle(fontSize: 15, color: p.label))),
            Padding(
              padding: const EdgeInsets.only(right: 14),
              child: Text(detail.toUpperCase(), style: condensed(12, weight: FontWeight.w600, tracking: 1, color: p.label3)),
            ),
          ]),
        ),
      ),
    );
  }
}

class _Banner extends StatelessWidget {
  final IconData icon;
  final String text;
  const _Banner({required this.icon, required this.text});

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(color: p.warningFill, borderRadius: BorderRadius.circular(10)),
      child: Row(children: [
        Icon(icon, size: 18, color: p.warning),
        const SizedBox(width: 8),
        Expanded(child: Text(text, style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: p.warning))),
      ]),
    );
  }
}
