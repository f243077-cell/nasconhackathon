import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/format.dart';
import '../../data/models.dart';
import '../../data/repository.dart';
import '../../widgets/async_view.dart';
import 'cart.dart';

/// Variant picker + quantity + Add to cart / Buy now.
class ProductScreen extends ConsumerStatefulWidget {
  final String productId;
  const ProductScreen({super.key, required this.productId});

  @override
  ConsumerState<ProductScreen> createState() => _ProductScreenState();
}

class _ProductScreenState extends ConsumerState<ProductScreen> {
  String? _variantId;
  int _qty = 1;

  @override
  Widget build(BuildContext context) {
    final product = ref.watch(productProvider(widget.productId));
    return Scaffold(
      appBar: AppBar(title: const Text('Product')),
      body: AsyncView<Product>(
        value: product,
        onRetry: () => ref.invalidate(productsProvider),
        builder: (p) {
          final variant = p.variants.where((v) => v.variantId == _variantId).firstOrNull ??
              p.variants.where((v) => v.stock > 0).firstOrNull;
          final inStock = variant != null && variant.stock > 0;
          return ListView(padding: const EdgeInsets.all(16), children: [
            const Icon(Icons.shopping_bag, size: 120, semanticLabel: 'Product image'),
            Text(p.name, style: Theme.of(context).textTheme.headlineSmall),
            const SizedBox(height: 4),
            Text(variant == null ? 'Sold out' : formatMoney(variant.priceMinor), style: Theme.of(context).textTheme.titleLarge),
            const SectionHeader('Choose an option'),
            Wrap(spacing: 8, runSpacing: 8, children: [
              for (final v in p.variants)
                ChoiceChip(
                  label: Text(v.stock > 0 ? (v.label.isEmpty ? 'Standard' : v.label) : '${v.label} · Out of stock'),
                  selected: v.variantId == variant?.variantId,
                  onSelected: v.stock > 0 ? (_) => setState(() => _variantId = v.variantId) : null,
                ),
            ]),
            const SectionHeader('Quantity'),
            QuantityStepper(
              value: _qty,
              max: variant == null ? 1 : variant.stock.clamp(1, 10),
              onChanged: (q) => setState(() => _qty = q),
            ),
            if (variant != null && variant.stock <= 3 && variant.stock > 0)
              Padding(padding: const EdgeInsets.only(top: 8), child: Text('Only ${variant.stock} left')),
            const SizedBox(height: 24),
            FilledButton.icon(
              onPressed: !inStock
                  ? null
                  : () {
                      ref.read(cartProvider.notifier).add(p, variant, _qty);
                      context.push('/cart');
                    },
              icon: const Icon(Icons.flash_on),
              label: const Text('Buy now'),
            ),
            const SizedBox(height: 12),
            OutlinedButton.icon(
              onPressed: !inStock
                  ? null
                  : () {
                      ref.read(cartProvider.notifier).add(p, variant, _qty);
                      showSuccess(context, 'Added to cart.');
                    },
              icon: const Icon(Icons.add_shopping_cart),
              label: const Text('Add to cart'),
            ),
          ]);
        },
      ),
    );
  }
}

class QuantityStepper extends StatelessWidget {
  final int value;
  final int max;
  final ValueChanged<int> onChanged;
  const QuantityStepper({super.key, required this.value, required this.onChanged, this.max = 10});

  @override
  Widget build(BuildContext context) => Row(mainAxisSize: MainAxisSize.min, children: [
        IconButton.outlined(
          tooltip: 'Decrease quantity',
          onPressed: value > 1 ? () => onChanged(value - 1) : null,
          icon: const Icon(Icons.remove),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: Text('$value', style: Theme.of(context).textTheme.titleLarge, semanticsLabel: 'Quantity $value'),
        ),
        IconButton.outlined(
          tooltip: 'Increase quantity',
          onPressed: value < max ? () => onChanged(value + 1) : null,
          icon: const Icon(Icons.add),
        ),
      ]);
}
