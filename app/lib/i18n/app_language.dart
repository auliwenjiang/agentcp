import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';

enum AppLanguage {
  en,
  zh,
}

class AppLanguageController extends ChangeNotifier {
  static const String _fileName = 'app_language.json';
  static const String _keyLanguage = 'language';

  AppLanguage _language = AppLanguage.zh;
  String? _storageFilePath;

  AppLanguage get language => _language;

  Locale get locale {
    switch (_language) {
      case AppLanguage.zh:
        return const Locale('zh');
      case AppLanguage.en:
        return const Locale('en');
    }
  }

  Future<void> load() async {
    try {
      final file = await _getStorageFile();
      _storageFilePath = file.path;
      if (!await file.exists()) {
        await _persist(file, _language);
        return;
      }

      final content = await file.readAsString();
      final decoded = jsonDecode(content);
      if (decoded is! Map<String, dynamic>) return;

      final raw = (decoded[_keyLanguage] ?? '').toString();
      final loaded = _parse(raw);
      if (loaded != null) {
        _language = loaded;
      }
    } catch (_) {
      // Fallback to default english.
    }
  }

  Future<void> setLanguage(AppLanguage language) async {
    if (_language == language) return;
    _language = language;
    notifyListeners();
    try {
      final file = await _getStorageFile();
      _storageFilePath = file.path;
      await _persist(file, language);
    } catch (_) {
      // Keep runtime state even if persistence fails.
    }
  }

  String getPersistedLocationLabel() {
    final path = _storageFilePath;
    if (path == null || path.isEmpty) return '';
    return path;
  }

  Future<File> _getStorageFile() async {
    final dir = await getApplicationDocumentsDirectory();
    return File('${dir.path}${Platform.pathSeparator}$_fileName');
  }

  Future<void> _persist(File file, AppLanguage language) async {
    if (!await file.parent.exists()) {
      await file.parent.create(recursive: true);
    }
    await file.writeAsString(
      jsonEncode(<String, dynamic>{
        _keyLanguage: language.name,
        'updatedAt': DateTime.now().toIso8601String(),
      }),
    );
  }

  AppLanguage? _parse(String value) {
    for (final item in AppLanguage.values) {
      if (item.name == value) return item;
    }
    return null;
  }
}

class AppLanguageScope extends InheritedWidget {
  final AppLanguageController controller;
  final AppLanguage language;

  const AppLanguageScope({
    super.key,
    required this.controller,
    required this.language,
    required super.child,
  });

  static AppLanguageController of(BuildContext context) {
    final scope = context.dependOnInheritedWidgetOfExactType<AppLanguageScope>();
    if (scope == null) {
      throw FlutterError('AppLanguageScope not found in widget tree.');
    }
    return scope.controller;
  }

  @override
  bool updateShouldNotify(AppLanguageScope oldWidget) {
    return controller != oldWidget.controller || language != oldWidget.language;
  }
}
