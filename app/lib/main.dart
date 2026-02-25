import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'i18n/app_language.dart';
import 'pages/agentcp_page.dart';
import 'pages/chat_page.dart';
import 'services/agentcp_service.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  AgentCPService.initCallbackHandler();
  final languageController = AppLanguageController();
  await languageController.load();
  runApp(MyApp(languageController: languageController));
}

class MyApp extends StatefulWidget {
  final AppLanguageController languageController;

  const MyApp({
    super.key,
    required this.languageController,
  });

  @override
  State<MyApp> createState() => _MyAppState();
}

class _MyAppState extends State<MyApp> with WidgetsBindingObserver {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _reconnectIfNeeded();
    }
  }

  Future<void> _reconnectIfNeeded() async {
    final aid = await AgentCPService.getCurrentAID();
    if (aid == null || aid.isEmpty) return;

    final online = await AgentCPService.isOnline();
    if (!online) {
      debugPrint('[MyApp] App resumed, WebSocket disconnected. Reconnecting...');
      await AgentCPService.online();
    }
  }

  @override
  Widget build(BuildContext context) {
    return AppLanguageScope(
      controller: widget.languageController,
      language: widget.languageController.language,
      child: AnimatedBuilder(
        animation: widget.languageController,
        builder: (context, _) {
          return MaterialApp(
            title: 'ACP',
            locale: widget.languageController.locale,
            supportedLocales: const [
              Locale('en'),
              Locale('zh'),
            ],
            localizationsDelegates: const [
              GlobalMaterialLocalizations.delegate,
              GlobalWidgetsLocalizations.delegate,
              GlobalCupertinoLocalizations.delegate,
            ],
            theme: ThemeData(
              colorScheme: ColorScheme.fromSeed(seedColor: Colors.deepPurple),
              useMaterial3: true,
            ),
            home: const AgentCPPage(),
            routes: {
              '/chat': (context) => const ChatPage(),
            },
            debugShowCheckedModeBanner: false,
          );
        },
      ),
    );
  }
}
