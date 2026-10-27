import React, { useState, useEffect, useRef } from 'react';
import {
  StyleSheet,
  Text,
  View,
  TextInput,
  TouchableOpacity,
  ScrollView,
  SafeAreaView,
  Alert,
  Animated,
  Easing,
  Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import { jarvisSocket, ConnectionStatus, JarvisMessage } from '../services/jarvisSocket';
import { makePhoneCall } from '../services/phoneCall';
import { resolveTargetToPhoneNumber, getContacts } from '../services/contactStorage';

export default function JarvisDashboard() {
  const router = useRouter();
  const [serverIp, setServerIp] = useState('192.168.1.10:8765');
  const [status, setStatus] = useState<ConnectionStatus>('DISCONNECTED');
  const [commandInput, setCommandInput] = useState('');
  const [logs, setLogs] = useState<string[]>([
    '[SYSTEM] JARVIS Mobile Bridge Initialized.',
    '[TIP] Enter your laptop IP below and tap CONNECT.',
  ]);

  const pulseAnim = useRef(new Animated.Value(1)).current;
  const rotateAnim = useRef(new Animated.Value(0)).current;

  const addLog = (text: string) => {
    const time = new Date().toLocaleTimeString([], { hour12: false });
    setLogs((prev) => [`[${time}] ${text}`, ...prev.slice(0, 30)]);
  };

  useEffect(() => {
    Animated.loop(
      Animated.sequence([
        Animated.timing(pulseAnim, {
          toValue: 1.15,
          duration: 1800,
          easing: Easing.inOut(Easing.ease),
          useNativeDriver: true,
        }),
        Animated.timing(pulseAnim, {
          toValue: 1.0,
          duration: 1800,
          easing: Easing.inOut(Easing.ease),
          useNativeDriver: true,
        }),
      ])
    ).start();

    Animated.loop(
      Animated.timing(rotateAnim, {
        toValue: 1,
        duration: 12000,
        easing: Easing.linear,
        useNativeDriver: true,
      })
    ).start();

    const unsubStatus = jarvisSocket.onStatusChange((newStatus) => {
      setStatus(newStatus);
      addLog(`Status changed: ${newStatus}`);
    });

    const unsubMessage = jarvisSocket.onMessage((data: JarvisMessage) => {
      if (data.type === 'CONNECTION_ESTABLISHED') {
        addLog(`Connected to LAPTOP JARVIS core.`);
      } else if (data.type === 'COMMAND_RECEIVED') {
        addLog(`Laptop processing: "${data.command}"`);
      }
    });

    const unsubCall = jarvisSocket.onCallRequest((target: string, raw?: string) => {
      addLog(`📞 CALL REQUEST FROM LAPTOP: "${target}"`);
      handleIncomingCallRequest(target);
    });

    return () => {
      unsubStatus();
      unsubMessage();
      unsubCall();
    };
  }, []);

  const handleIncomingCallRequest = async (target: string) => {
    const resolved = resolveTargetToPhoneNumber(target);

    if (resolved) {
      addLog(`✅ Resolved "${target}" to ${resolved.contactName} (${resolved.phoneNumber})`);
      const success = await makePhoneCall(resolved.phoneNumber, resolved.contactName);
      if (success) {
        addLog(`📞 Placed call to ${resolved.contactName} (${resolved.phoneNumber})`);
      }
    } else {
      addLog(`⚠️ Unknown contact: "${target}". Please add to Speed Dial.`);
      Alert.alert(
        'Contact Not Found',
        `Jarvis heard "Call ${target}", but "${target}" was not found in your Speed Dial directory.`,
        [
          { text: 'Add Contact', onPress: () => router.push('/contacts') },
          { text: 'Dismiss', style: 'cancel' },
        ]
      );
    }
  };

  const toggleConnection = () => {
    if (status === 'CONNECTED' || status === 'CONNECTING') {
      jarvisSocket.disconnect();
      addLog('Disconnected by user.');
    } else {
      if (!serverIp.trim()) {
        Alert.alert('IP Required', 'Please enter your laptop IP address.');
        return;
      }
      addLog(`Connecting to ${serverIp}...`);
      jarvisSocket.connect(serverIp);
    }
  };

  const sendCustomCommand = (cmdText?: string) => {
    const cmd = (cmdText || commandInput).trim();
    if (!cmd) return;

    if (status !== 'CONNECTED') {
      const isCall = cmd.toLowerCase().startsWith('call ') || cmd.toLowerCase().startsWith('dial ');
      if (isCall) {
        const target = cmd.replace(/^(call|dial)\s+/i, '');
        handleIncomingCallRequest(target);
        if (!cmdText) setCommandInput('');
        return;
      }

      Alert.alert('Offline', 'Connect to your laptop first to send remote commands.');
      return;
    }

    jarvisSocket.sendCommandToLaptop(cmd);
    addLog(`Sent to Laptop: "${cmd}"`);
    if (!cmdText) setCommandInput('');
  };

  const triggerCallDirect = (name: string) => {
    handleIncomingCallRequest(name);
  };

  const spin = rotateAnim.interpolate({
    inputRange: [0, 1],
    outputRange: ['0deg', '360deg'],
  });

  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.container}>
        <View style={styles.header}>
          <View>
            <Text style={styles.headerTitle}>J.A.R.V.I.S</Text>
            <Text style={styles.headerSubtitle}>NEURAL MOBILE BRIDGE</Text>
          </View>

          <View style={[styles.statusBadge, status === 'CONNECTED' ? styles.statusOnline : status === 'CONNECTING' ? styles.statusPending : styles.statusOffline]}>
            <View style={[styles.statusDot, status === 'CONNECTED' ? styles.dotOnline : status === 'CONNECTING' ? styles.dotPending : styles.dotOffline]} />
            <Text style={styles.statusText}>{status}</Text>
          </View>
        </View>

        <View style={styles.ipContainer}>
          <TextInput
            style={styles.ipInput}
            value={serverIp}
            onChangeText={setServerIp}
            placeholder="192.168.1.XX:8765"
            placeholderTextColor="#475569"
            autoCapitalize="none"
            autoCorrect={false}
          />
          <TouchableOpacity
            style={[styles.connectButton, status === 'CONNECTED' ? styles.disconnectButton : null]}
            onPress={toggleConnection}
          >
            <Text style={styles.connectButtonText}>
              {status === 'CONNECTED' ? 'DISCONNECT' : status === 'CONNECTING' ? 'CANCEL' : 'CONNECT'}
            </Text>
          </TouchableOpacity>
        </View>

        <View style={styles.coreContainer}>
          <Animated.View
            style={[
              styles.outerRing,
              {
                transform: [{ scale: pulseAnim }, { rotate: spin }],
                borderColor: status === 'CONNECTED' ? '#00E5FF' : '#334155',
              },
            ]}
          />
          <Animated.View
            style={[
              styles.innerCore,
              {
                transform: [{ scale: pulseAnim }],
                shadowColor: status === 'CONNECTED' ? '#00E5FF' : '#64748B',
              },
            ]}
          >
            <Text style={styles.coreText}>MARK 42</Text>
            <Text style={styles.coreSubText}>
              {status === 'CONNECTED' ? 'READY' : 'STANDBY'}
            </Text>
          </Animated.View>
        </View>

        <Text style={styles.sectionLabel}>VOICE CALL SHORTCUTS</Text>
        <View style={styles.shortcutRow}>
          <TouchableOpacity
            style={[styles.shortcutBtn, styles.callBtnMom]}
            onPress={() => triggerCallDirect('Mom')}
          >
            <Text style={styles.shortcutIcon}>📞</Text>
            <Text style={styles.shortcutText}>Call Mom</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.shortcutBtn, styles.callBtnRohan]}
            onPress={() => triggerCallDirect('Rohan')}
          >
            <Text style={styles.shortcutIcon}>📞</Text>
            <Text style={styles.shortcutText}>Call Rohan</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.shortcutBtn}
            onPress={() => router.push('/contacts')}
          >
            <Text style={styles.shortcutIcon}>📖</Text>
            <Text style={styles.shortcutText}>Directory</Text>
          </TouchableOpacity>
        </View>

        <View style={styles.navRow}>
          <TouchableOpacity
            style={styles.navBtn}
            onPress={() => sendCustomCommand('stop music')}
          >
            <Text style={styles.navBtnText}>⏹ Stop Song</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.navBtn}
            onPress={() => sendCustomCommand('take picture')}
          >
            <Text style={styles.navBtnText}>📸 Take Photo</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.navBtn, styles.navBtnSpecial]}
            onPress={() => router.push('/remote')}
          >
            <Text style={styles.navBtnSpecialText}>⚡ Laptop Controls</Text>
          </TouchableOpacity>
        </View>

        <View style={styles.commandRow}>
          <TextInput
            style={styles.commandInput}
            value={commandInput}
            onChangeText={setCommandInput}
            placeholder="Type command (e.g. call rohan, open chrome)..."
            placeholderTextColor="#475569"
            onSubmitEditing={() => sendCustomCommand()}
          />
          <TouchableOpacity style={styles.sendButton} onPress={() => sendCustomCommand()}>
            <Text style={styles.sendButtonText}>SEND</Text>
          </TouchableOpacity>
        </View>

        <View style={styles.terminalContainer}>
          <View style={styles.terminalHeader}>
            <Text style={styles.terminalTitle}>TELEMETRY LOGS</Text>
            <TouchableOpacity onPress={() => setLogs(['[CLEARED]'])}>
              <Text style={styles.clearLogsText}>Clear</Text>
            </TouchableOpacity>
          </View>
          <ScrollView style={styles.terminalScroll} nestedScrollEnabled>
            {logs.map((log, index) => (
              <Text
                key={index}
                style={[
                  styles.logLine,
                  log.includes('CALL') ? styles.logCall : log.includes('✅') ? styles.logSuccess : log.includes('⚠️') ? styles.logWarn : null,
                ]}
              >
                {log}
              </Text>
            ))}
          </ScrollView>
        </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: '#040711',
  },
  container: {
    flex: 1,
    paddingHorizontal: 16,
    paddingTop: Platform.OS === 'android' ? 36 : 10,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  headerTitle: {
    fontSize: 26,
    fontWeight: '900',
    color: '#38BDF8',
    letterSpacing: 4,
  },
  headerSubtitle: {
    fontSize: 10,
    color: '#64748B',
    letterSpacing: 2,
    marginTop: 2,
  },
  statusBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 20,
    borderWidth: 1,
  },
  statusOnline: {
    backgroundColor: 'rgba(16, 185, 129, 0.1)',
    borderColor: '#10B981',
  },
  statusPending: {
    backgroundColor: 'rgba(245, 158, 11, 0.1)',
    borderColor: '#F59E0B',
  },
  statusOffline: {
    backgroundColor: 'rgba(239, 68, 68, 0.1)',
    borderColor: '#EF4444',
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginRight: 6,
  },
  dotOnline: { backgroundColor: '#10B981' },
  dotPending: { backgroundColor: '#F59E0B' },
  dotOffline: { backgroundColor: '#EF4444' },
  statusText: {
    fontSize: 11,
    fontWeight: '700',
    color: '#E2E8F0',
    letterSpacing: 1,
  },
  ipContainer: {
    flexDirection: 'row',
    backgroundColor: '#0B1120',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#1E293B',
    padding: 4,
    marginBottom: 16,
  },
  ipInput: {
    flex: 1,
    color: '#F8FAFC',
    paddingHorizontal: 12,
    fontSize: 14,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
  },
  connectButton: {
    backgroundColor: '#0284C7',
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 8,
    justifyContent: 'center',
  },
  disconnectButton: {
    backgroundColor: '#DC2626',
  },
  connectButtonText: {
    color: '#FFFFFF',
    fontWeight: '700',
    fontSize: 12,
    letterSpacing: 1,
  },
  coreContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    height: 160,
    marginVertical: 4,
  },
  outerRing: {
    position: 'absolute',
    width: 140,
    height: 140,
    borderRadius: 70,
    borderWidth: 2,
    borderStyle: 'dashed',
  },
  innerCore: {
    width: 100,
    height: 100,
    borderRadius: 50,
    backgroundColor: '#090E1A',
    borderWidth: 2,
    borderColor: '#0284C7',
    alignItems: 'center',
    justifyContent: 'center',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.8,
    shadowRadius: 16,
    elevation: 10,
  },
  coreText: {
    color: '#38BDF8',
    fontSize: 13,
    fontWeight: '900',
    letterSpacing: 2,
  },
  coreSubText: {
    color: '#94A3B8',
    fontSize: 9,
    letterSpacing: 1,
    marginTop: 2,
  },
  sectionLabel: {
    color: '#64748B',
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 1.5,
    marginBottom: 8,
  },
  shortcutRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 10,
  },
  shortcutBtn: {
    flex: 1,
    backgroundColor: '#0F172A',
    borderWidth: 1,
    borderColor: '#1E293B',
    borderRadius: 10,
    paddingVertical: 10,
    alignItems: 'center',
    marginHorizontal: 4,
  },
  callBtnMom: {
    borderColor: 'rgba(236, 72, 153, 0.4)',
    backgroundColor: 'rgba(236, 72, 153, 0.08)',
  },
  callBtnRohan: {
    borderColor: 'rgba(56, 189, 248, 0.4)',
    backgroundColor: 'rgba(56, 189, 248, 0.08)',
  },
  shortcutIcon: {
    fontSize: 18,
    marginBottom: 4,
  },
  shortcutText: {
    color: '#F1F5F9',
    fontSize: 12,
    fontWeight: '600',
  },
  navRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 12,
  },
  navBtn: {
    backgroundColor: '#0F172A',
    borderWidth: 1,
    borderColor: '#1E293B',
    paddingVertical: 8,
    paddingHorizontal: 10,
    borderRadius: 8,
  },
  navBtnText: {
    color: '#CBD5E1',
    fontSize: 11,
    fontWeight: '600',
  },
  navBtnSpecial: {
    borderColor: '#0284C7',
    backgroundColor: 'rgba(2, 132, 199, 0.15)',
  },
  navBtnSpecialText: {
    color: '#38BDF8',
    fontSize: 11,
    fontWeight: '700',
  },
  commandRow: {
    flexDirection: 'row',
    backgroundColor: '#0B1120',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#1E293B',
    padding: 4,
    marginBottom: 12,
  },
  commandInput: {
    flex: 1,
    color: '#F8FAFC',
    paddingHorizontal: 12,
    fontSize: 13,
  },
  sendButton: {
    backgroundColor: '#0284C7',
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 8,
    justifyContent: 'center',
  },
  sendButtonText: {
    color: '#FFFFFF',
    fontWeight: '700',
    fontSize: 11,
    letterSpacing: 1,
  },
  terminalContainer: {
    flex: 1,
    backgroundColor: '#030712',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#1E293B',
    padding: 10,
    marginBottom: 8,
  },
  terminalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    borderBottomWidth: 1,
    borderBottomColor: '#1E293B',
    paddingBottom: 6,
    marginBottom: 6,
  },
  terminalTitle: {
    color: '#64748B',
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 1.5,
  },
  clearLogsText: {
    color: '#475569',
    fontSize: 10,
  },
  terminalScroll: {
    flex: 1,
  },
  logLine: {
    color: '#94A3B8',
    fontSize: 11,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
    marginBottom: 4,
  },
  logCall: {
    color: '#F472B6',
    fontWeight: '700',
  },
  logSuccess: {
    color: '#34D399',
  },
  logWarn: {
    color: '#FBBF24',
  },
});
