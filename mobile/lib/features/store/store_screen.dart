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

class StoreScreen extends ConsumerStatefulWidget {
  const StoreScreen({super.key});

  @override
  ConsumerState<StoreScreen> createState() => _StoreScreenState();
}

class _StoreScreenState extends ConsumerState<StoreScreen> {
  String _type = 'all';

  @override
  Widget build(BuildContext context) {
    final products = ref.watch(productsProvider);
    final cartCount = ref.watch(cartProvider).fold<int>(0, (n, l) => n + l.quantity);
    return LargeTitlePage(
      title: 'Store',
      trailing: IconButton(
        tooltip: cartCount == 0 ? 'Cart' : 'Cart, $cartCount items',
        onPressed: () => context.push('/cart'),
        icon: Badge(isLabelVisible: cartCount > 0, label: Text('$cartCount'), child: const Icon(Icons.shopping_cart_rounded)),
      ),
      onRefresh: () => ref.refresh(productsProvider.future),
      slivers: [
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 20),
            child: Segmented<String>(
              value: _type,
              options: const {'all': 'All', 'apparel': 'Apparel', 'accessory': 'Gear', 'digital': 'Digital'},
              onChanged: (v) => setState(() => _type = v),
            ),
          ),
        ),
        AsyncSliver<List<Product>>(
          value: products,
          onRetry: () => ref.invalidate(productsProvider),
          isEmpty: (all) => (_type == 'all' ? all : all.where((p) => p.type == _type)).isEmpty,
          emptyMessage: _type == 'all' ? 'No products yet' : 'Nothing in this category yet',
          emptyIcon: Icons.shopping_bag_rounded,
          builder: (all) {
            final list = _type == 'all' ? all : all.where((p) => p.type == _type).toList();
            return SliverPadding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              sliver: SliverGrid.builder(
                gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
                  maxCrossAxisExtent: 240,
                  mainAxisSpacing: 20,
                  crossAxisSpacing: 14,
                  childAspectRatio: 0.72,
                ),
                itemCount: list.length,
                itemBuilder: (_, i) => _ProductTile(product: list[i]),
              ),
            );
          },
        ),
      ],
    );
  }
}

/// Image, name, price. The tile is the button; no card chrome around it.
class _ProductTile extends StatelessWidget {
  final Product product;
  const _ProductTile({required this.product});

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final soldOut = product.variants.every((v) => v.stock <= 0);
    return Semantics(
      button: true,
      label: '${product.name}, from ${formatMoney(product.fromPriceMinor)}${soldOut ? ', sold out' : ''}',
      excludeSemantics: true,
      child: InkWell(
        borderRadius: BorderRadius.circular(14),
        onTap: () => context.push('/product/${product.productId}'),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Expanded(
            child: ClipRRect(
              borderRadius: BorderRadius.circular(14),
              child: SizedBox(width: double.infinity, child: ProductArtwork(type: product.type)),
            ),
          ),
          const SizedBox(height: 10),
          Text(product.name, style: t.titleMedium, maxLines: 2, overflow: TextOverflow.ellipsis),
          const SizedBox(height: 2),
          Text(
            soldOut ? 'Sold out' : 'From ${formatMoney(product.fromPriceMinor)}',
            style: t.bodyMedium!.copyWith(fontFeatures: tabular),
          ),
        ]),
      ),
    );
  }
}
