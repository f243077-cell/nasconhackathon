import 'package:dio/dio.dart';
import 'package:flutter/material.dart';

import '../../core/config.dart';
import '../../core/theme.dart';
import '../../widgets/async_view.dart';
import '../../widgets/ui.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
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
    if (mounted) showSuccess(context, 'Server address saved.');
  }

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    return Scaffold(
      appBar: AppBar(title: const Text('Server')),
      body: ListView(padding: const EdgeInsets.only(top: 16), children: [
        Section(
          header: 'Server address',
          footer: 'Emulator: http://10.0.2.2:8080\nPhone: http://<laptop IP>:8080 on the same Wi-Fi',
          children: [
            TextField(
              controller: _url,
              keyboardType: TextInputType.url,
              autocorrect: false,
              style: Theme.of(context).textTheme.bodyLarge!.copyWith(fontFeatures: tabular),
              decoration: const InputDecoration(
                hintText: 'http://10.0.2.2:8080',
                filled: false,
                border: InputBorder.none,
                enabledBorder: InputBorder.none,
                focusedBorder: InputBorder.none,
              ),
            ),
          ],
        ),
        Section(children: [
          ListTile(
            title: Text('Test Connection', style: TextStyle(color: p.accent)),
            onTap: _testing ? null : _test,
            trailing: _testing
                ? const SizedBox.square(dimension: 20, child: CircularProgressIndicator(strokeWidth: 2))
                : _reachable == null
                    ? null
                    : Row(mainAxisSize: MainAxisSize.min, children: [
                        Icon(
                          _reachable! ? Icons.check_circle_rounded : Icons.error_rounded,
                          size: 18,
                          color: _reachable! ? p.success : p.danger,
                        ),
                        const SizedBox(width: 6),
                        Text(_reachable! ? 'Connected' : "Can't reach server"),
                      ]),
          ),
        ]),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: PrimaryButton(label: 'Save', onPressed: _save),
        ),
      ]),
    );
  }
}
