import React from 'react';
import {
  StyleSheet,
  Text,
  View,
  TouchableOpacity,
  ScrollView,
  SafeAreaView,
  Alert,
} from 'react-native';
import { jarvisSocket } from '../services/jarvisSocket';

export default function RemoteScreen() {
  const sendCommand = (cmd: string, label: string) => {
    if (jarvisSocket.getStatus() !== 'CONNECTED') {
      Alert.alert('Not Connected', 'Please connect to your laptop on the home screen first.');
      return;
    }
    jarvisSocket.sendCommandToLaptop(cmd);
    Alert.alert('Command Sent', `Dispatched "${label}" to Laptop.`);
  };

  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView style={styles.container} contentContainerStyle={styles.content}>
        <Text style={styles.sectionHeader}>APPLICATIONS</Text>
        <View style={styles.grid}>
          <TouchableOpacity
            style={styles.card}
            onPress={() => sendCommand('open chrome', 'Open Chrome')}
          >
            <Text style={styles.icon}>🌐</Text>
            <Text style={styles.title}>Chrome Browser</Text>
            <Text style={styles.cmd}>"open chrome"</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.card}
            onPress={() => sendCommand('open youtube', 'Open YouTube')}
          >
            <Text style={styles.icon}>▶️</Text>
            <Text style={styles.title}>YouTube</Text>
            <Text style={styles.cmd}>"open youtube"</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.card}
            onPress={() => sendCommand('open vscode', 'Open VS Code')}
          >
            <Text style={styles.icon}>💻</Text>
            <Text style={styles.title}>VS Code</Text>
            <Text style={styles.cmd}>"open vscode"</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.card}
            onPress={() => sendCommand('open notepad', 'Open Notepad')}
          >
            <Text style={styles.icon}>📝</Text>
            <Text style={styles.title}>Notepad</Text>
            <Text style={styles.cmd}>"open notepad"</Text>
          </TouchableOpacity>
        </View>

        <Text style={styles.sectionHeader}>CAMERA & VISION</Text>
        <View style={styles.grid}>
          <TouchableOpacity
            style={styles.card}
            onPress={() => sendCommand('take a picture', 'Take Picture')}
          >
            <Text style={styles.icon}>📸</Text>
            <Text style={styles.title}>Take Photo</Text>
            <Text style={styles.cmd}>Saves to Pictures/Jarvis</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.card}
            onPress={() => sendCommand('show me my recent picture', 'Show Recent Photo')}
          >
            <Text style={styles.icon}>🖼️</Text>
            <Text style={styles.title}>Show Last Photo</Text>
            <Text style={styles.cmd}>Opens in Explorer</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.card}
            onPress={() => sendCommand('start video recording', 'Start Recording')}
          >
            <Text style={styles.icon}>🔴</Text>
            <Text style={styles.title}>Record Video</Text>
            <Text style={styles.cmd}>"start video recording"</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.card}
            onPress={() => sendCommand('stop video recording', 'Stop Recording')}
          >
            <Text style={styles.icon}>⏹️</Text>
            <Text style={styles.title}>Stop Recording</Text>
            <Text style={styles.cmd}>"stop recording"</Text>
          </TouchableOpacity>
        </View>

        <Text style={styles.sectionHeader}>AUDIO & POWER</Text>
        <View style={styles.grid}>
          <TouchableOpacity
            style={styles.card}
            onPress={() => sendCommand('stop the music', 'Stop Song')}
          >
            <Text style={styles.icon}>⏹️</Text>
            <Text style={styles.title}>Stop Audio</Text>
            <Text style={styles.cmd}>"stop the music"</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.card}
            onPress={() => sendCommand('who am i', 'Who Am I')}
          >
            <Text style={styles.icon}>🤖</Text>
            <Text style={styles.title}>Jarvis Identity</Text>
            <Text style={styles.cmd}>"who am i"</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.card, styles.dangerCard]}
            onPress={() => sendCommand('close all', 'Close All Apps')}
          >
            <Text style={styles.icon}>❌</Text>
            <Text style={styles.title}>Close All Apps</Text>
            <Text style={styles.cmd}>"close all"</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.card, styles.dangerCard]}
            onPress={() => sendCommand('sleep', 'Sleep Jarvis')}
          >
            <Text style={styles.icon}>💤</Text>
            <Text style={styles.title}>Sleep Jarvis</Text>
            <Text style={styles.cmd}>"sleep"</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
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
  },
  content: {
    padding: 16,
    paddingBottom: 40,
  },
  sectionHeader: {
    color: '#64748B',
    fontSize: 11,
    fontWeight: '800',
    letterSpacing: 2,
    marginTop: 10,
    marginBottom: 10,
  },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    marginBottom: 10,
  },
  card: {
    width: '48%',
    backgroundColor: '#0B1120',
    borderWidth: 1,
    borderColor: '#1E293B',
    borderRadius: 12,
    padding: 14,
    marginBottom: 12,
  },
  dangerCard: {
    borderColor: 'rgba(239, 68, 68, 0.4)',
    backgroundColor: 'rgba(239, 68, 68, 0.06)',
  },
  icon: {
    fontSize: 24,
    marginBottom: 8,
  },
  title: {
    color: '#F1F5F9',
    fontSize: 14,
    fontWeight: '700',
  },
  cmd: {
    color: '#64748B',
    fontSize: 10,
    marginTop: 4,
    fontStyle: 'italic',
  },
});
