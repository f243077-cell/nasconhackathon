import 'package:dio/dio.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/config.dart';
import '../../core/theme.dart';
import '../../data/sync_queue.dart';
import '../../widgets/async_view.dart';
import '../../widgets/ui.dart';

class SettingsScreen extends ConsumerStatefulWidget {
  const SettingsScreen({super.key});

  @override
  ConsumerState<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends ConsumerState<SettingsScreen> {
  final _url = TextEditingController();
  bool _testing = false;
  bool? _reachable;

  @override
  void initState() {
    super.initState();
    ServerConfig.load().then((u) => _url.text = u);
  }

  @override
  void dispose() {
    _url.dispose();
    super.dispose();
  }

  Future<void> _test() async {
    setState(() {
      _testing = true;
      _reachable = null;
    });
    var ok = false;
    try {
      await Dio(BaseOptions(connectTimeout: const Duration(seconds: 3), receiveTimeout: const Duration(seconds: 3)))
          .get('${_url.text.trim()}/api/v1/ping');
      ok = true;
    } catch (_) {}
    if (mounted) {
      setState(() {
        _testing = false;
        _reachable = ok;
      });
    }
  }

  Future<void> _save() async {
    await ServerConfig.save(_url.text);
    ref.read(syncProvider.notifier).recheck(); // new server: re-test reachability and flush the queue
    if (mounted) showSuccess(context, 'Server address saved.');
  }

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    return FlatPage(
      title: 'Server',
      backFallback: '/login',
      actions: [PrimaryButton(label: 'Save', onPressed: _save)],
      children: [
        LabeledField(
          label: 'Server address',
          child: TextField(
            controller: _url,
            keyboardType: TextInputType.url,
            autocorrect: false,
            style: const TextStyle(fontSize: 16, fontFeatures: tabular),
            decoration: const InputDecoration(hintText: 'http://10.0.2.2:8080'),
          ),
        ),
        const SizedBox(height: 8),
        Text(
          'Emulator: http://10.0.2.2:8080\nPhone: http://<laptop IP>:8080 on the same Wi-Fi',
          style: TextStyle(fontSize: 13, color: p.label3, height: 1.5),
        ),
        const SizedBox(height: 18),
        SecondaryButton(label: 'Test connection', onPressed: _testing ? null : _test),
        const SizedBox(height: 12),
        if (_testing)
          Center(child: CupertinoActivityIndicator(color: p.label3))
        else if (_reachable != null)
          Row(mainAxisAlignment: MainAxisAlignment.center, children: [
            Icon(_reachable! ? Icons.check_circle_rounded : Icons.error_rounded, size: 18, color: _reachable! ? p.success : p.danger),
            const SizedBox(width: 6),
            Text(_reachable! ? 'Connected' : "Can't reach server", style: TextStyle(fontSize: 15, color: p.label)),
          ]),
      ],
    );
  }
}
