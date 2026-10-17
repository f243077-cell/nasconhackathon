import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/format.dart';
import '../../core/theme.dart';
import '../../data/models.dart';
import '../../data/repository.dart';
import '../../widgets/async_view.dart';
import '../../widgets/ui.dart';
import 'cart.dart';

/// Artwork, price, option picker and quantity; Buy Now stays within thumb reach at the bottom.
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
    final t = Theme.of(context).textTheme;
    final p = context.palette;
    final p0 = product.value;
    final variant = p0 == null
        ? null
        : p0.variants.where((v) => v.variantId == _variantId).firstOrNull ?? p0.variants.where((v) => v.stock > 0).firstOrNull;
    final inStock = variant != null && variant.stock > 0;

    return Scaffold(
      appBar: AppBar(title: Text(p0?.name ?? 'Product')),
      bottomNavigationBar: p0 == null
          ? null
          : BottomActionBar(children: [
              PrimaryButton(
                label: inStock ? 'Buy Now' : 'Sold Out',
                onPressed: !inStock
                    ? null
                    : () {
                        ref.read(cartProvider.notifier).add(p0, variant, _qty);
                        context.push('/cart');
                      },
              ),
              SecondaryButton(
                label: 'Add to Cart',
                icon: Icons.add_shopping_cart_rounded,
                onPressed: !inStock
                    ? null
                    : () {
                        ref.read(cartProvider.notifier).add(p0, variant, _qty);
                        showSuccess(context, 'Added to cart.');
                      },
              ),
            ]),
      body: AsyncView<Product>(
        value: product,
        onRetry: () => ref.invalidate(productsProvider),
        builder: (prod) => ListView(padding: const EdgeInsets.only(bottom: 24), children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(16),
              child: AspectRatio(aspectRatio: 1.25, child: ProductArtwork(type: prod.type, iconSize: 72)),
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 20, 20, 24),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(prod.name, style: t.headlineMedium),
              const SizedBox(height: 6),
              Text(
                variant == null ? 'Sold out' : formatMoney(variant.priceMinor),
                style: t.titleLarge!.copyWith(fontFeatures: tabular),
              ),
              if (variant != null && variant.stock > 0 && variant.stock <= 3) ...[
                const SizedBox(height: 6),
                Row(children: [
                  Icon(Icons.schedule_rounded, size: 16, color: p.warning),
                  const SizedBox(width: 6),
                  Text('Only ${variant.stock} left', style: t.bodyMedium!.copyWith(color: p.warning)),
                ]),
              ],
            ]),
          ),
          if (prod.variants.length > 1)
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('Option', style: t.titleMedium),
                const SizedBox(height: 12),
                Wrap(spacing: 10, runSpacing: 10, children: [
                  for (final v in prod.variants)
                    OptionPill(
                      label: v.label.isEmpty ? 'Standard' : v.label,
                      selected: v.variantId == variant?.variantId,
                      onTap: v.stock > 0 ? () => setState(() => _variantId = v.variantId) : null,
                    ),
                ]),
                if (prod.variants.any((v) => v.stock <= 0)) ...[
                  const SizedBox(height: 8),
                  Text('Crossed-out options are out of stock.', style: t.bodySmall),
                ],
              ]),
            ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 20),
            child: Row(children: [
              Expanded(child: Text('Quantity', style: t.titleMedium)),
              QuantityStepper(
                value: _qty,
                max: variant == null ? 1 : variant.stock.clamp(1, 10),
                onChanged: (q) => setState(() => _qty = q),
              ),
            ]),
          ),
        ]),
      ),
    );
  }
}
