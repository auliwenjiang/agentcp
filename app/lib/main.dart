import 'package:flutter/material.dart';
import 'pages/agentcp_page.dart';
import 'pages/chat_page.dart';
import 'services/agentcp_service.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  AgentCPService.initCallbackHandler();
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Evol',
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
  }
}
