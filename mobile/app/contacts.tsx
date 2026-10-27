import React, { useState } from 'react';
import {
  StyleSheet,
  Text,
  View,
  TextInput,
  TouchableOpacity,
  FlatList,
  Alert,
  SafeAreaView,
  Platform,
} from 'react-native';
import { getContacts, addContact, deleteContact, Contact } from '../services/contactStorage';
import { makePhoneCall } from '../services/phoneCall';

export default function ContactsScreen() {
  const [contacts, setContacts] = useState<Contact[]>(getContacts());
  const [nameInput, setNameInput] = useState('');
  const [phoneInput, setPhoneInput] = useState('');
  const [relationInput, setRelationInput] = useState('');
  const [isAdding, setIsAdding] = useState(false);

  const refreshList = () => {
    setContacts([...getContacts()]);
  };

  const handleAdd = () => {
    if (!nameInput.trim() || !phoneInput.trim()) {
      Alert.alert('Required Fields', 'Please provide both a contact name and a phone number.');
      return;
    }
    addContact(nameInput, phoneInput, relationInput);
    setNameInput('');
    setPhoneInput('');
    setRelationInput('');
    setIsAdding(false);
    refreshList();
    Alert.alert('Saved', `Contact "${nameInput}" added to JARVIS Speed Dial.`);
  };

  const handleDelete = (id: string, name: string) => {
    Alert.alert('Delete Contact', `Remove ${name} from Speed Dial?`, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: () => {
          deleteContact(id);
          refreshList();
        },
      },
    ]);
  };

  const handleTestCall = (contact: Contact) => {
    makePhoneCall(contact.phone, contact.name);
  };

  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.container}>
        <View style={styles.introHeader}>
          <Text style={styles.introTitle}>VOICE SPEED DIAL DIRECTORY</Text>
          <Text style={styles.introSubtitle}>
            When you say "Call &lt;Name&gt;" on your laptop or phone, JARVIS matches from this list.
          </Text>
        </View>

        {isAdding ? (
          <View style={styles.addCard}>
            <Text style={styles.addCardTitle}>NEW SPEED DIAL ENTRY</Text>
            <TextInput
              style={styles.input}
              placeholder="Name (e.g. Mom, Rohan, Dad)"
              placeholderTextColor="#475569"
              value={nameInput}
              onChangeText={setNameInput}
            />
            <TextInput
              style={styles.input}
              placeholder="Phone Number (e.g. +91 9876543210)"
              placeholderTextColor="#475569"
              keyboardType="phone-pad"
              value={phoneInput}
              onChangeText={setPhoneInput}
            />
            <TextInput
              style={styles.input}
              placeholder="Relation / Tag (e.g. Mother, Friend)"
              placeholderTextColor="#475569"
              value={relationInput}
              onChangeText={setRelationInput}
            />
            <View style={styles.addBtnRow}>
              <TouchableOpacity style={styles.cancelBtn} onPress={() => setIsAdding(false)}>
                <Text style={styles.cancelBtnText}>CANCEL</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.saveBtn} onPress={handleAdd}>
                <Text style={styles.saveBtnText}>SAVE CONTACT</Text>
              </TouchableOpacity>
            </View>
          </View>
        ) : (
          <TouchableOpacity style={styles.newEntryBtn} onPress={() => setIsAdding(true)}>
            <Text style={styles.newEntryBtnText}>+ ADD SPEED DIAL CONTACT</Text>
          </TouchableOpacity>
        )}

        <FlatList
          data={contacts}
          keyExtractor={(item) => item.id}
          contentContainerStyle={styles.listContent}
          renderItem={({ item }) => (
            <View style={styles.contactCard}>
              <View style={[styles.avatar, { backgroundColor: item.avatarColor || '#3B82F6' }]}>
                <Text style={styles.avatarText}>{item.name.charAt(0).toUpperCase()}</Text>
              </View>

              <View style={styles.contactInfo}>
                <View style={styles.nameRow}>
                  <Text style={styles.contactName}>{item.name}</Text>
                  {item.relationship ? (
                    <View style={styles.tag}>
                      <Text style={styles.tagText}>{item.relationship}</Text>
                    </View>
                  ) : null}
                </View>
                <Text style={styles.contactPhone}>{item.phone}</Text>
                <Text style={styles.triggerHint}>Say: "Jarvis call {item.name.toLowerCase()}"</Text>
              </View>

              <View style={styles.actionCol}>
                <TouchableOpacity
                  style={styles.callActionButton}
                  onPress={() => handleTestCall(item)}
                >
                  <Text style={styles.callActionText}>CALL</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={styles.deleteButton}
                  onPress={() => handleDelete(item.id, item.name)}
                >
                  <Text style={styles.deleteText}>✕</Text>
                </TouchableOpacity>
              </View>
            </View>
          )}
        />
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
    paddingTop: 10,
  },
  introHeader: {
    marginBottom: 14,
  },
  introTitle: {
    color: '#38BDF8',
    fontSize: 14,
    fontWeight: '800',
    letterSpacing: 2,
  },
  introSubtitle: {
    color: '#64748B',
    fontSize: 12,
    marginTop: 4,
    lineHeight: 16,
  },
  newEntryBtn: {
    backgroundColor: '#0F172A',
    borderWidth: 1,
    borderColor: '#0284C7',
    paddingVertical: 12,
    borderRadius: 10,
    alignItems: 'center',
    marginBottom: 14,
  },
  newEntryBtnText: {
    color: '#38BDF8',
    fontSize: 12,
    fontWeight: '700',
    letterSpacing: 1,
  },
  addCard: {
    backgroundColor: '#0B1120',
    borderWidth: 1,
    borderColor: '#1E293B',
    borderRadius: 12,
    padding: 14,
    marginBottom: 14,
  },
  addCardTitle: {
    color: '#E2E8F0',
    fontSize: 12,
    fontWeight: '700',
    letterSpacing: 1.5,
    marginBottom: 10,
  },
  input: {
    backgroundColor: '#030712',
    borderWidth: 1,
    borderColor: '#1E293B',
    color: '#F8FAFC',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 8,
    fontSize: 13,
    marginBottom: 8,
  },
  addBtnRow: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    marginTop: 4,
  },
  cancelBtn: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    marginRight: 8,
    justifyContent: 'center',
  },
  cancelBtnText: {
    color: '#94A3B8',
    fontSize: 11,
    fontWeight: '600',
  },
  saveBtn: {
    backgroundColor: '#0284C7',
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 8,
  },
  saveBtnText: {
    color: '#FFFFFF',
    fontSize: 11,
    fontWeight: '700',
  },
  listContent: {
    paddingBottom: 20,
  },
  contactCard: {
    flexDirection: 'row',
    backgroundColor: '#090D16',
    borderWidth: 1,
    borderColor: '#1E293B',
    borderRadius: 12,
    padding: 12,
    alignItems: 'center',
    marginBottom: 10,
  },
  avatar: {
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 12,
  },
  avatarText: {
    color: '#FFFFFF',
    fontSize: 18,
    fontWeight: '800',
  },
  contactInfo: {
    flex: 1,
  },
  nameRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  contactName: {
    color: '#F1F5F9',
    fontSize: 15,
    fontWeight: '700',
    marginRight: 8,
  },
  tag: {
    backgroundColor: '#1E293B',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  tagText: {
    color: '#94A3B8',
    fontSize: 10,
    fontWeight: '600',
  },
  contactPhone: {
    color: '#38BDF8',
    fontSize: 13,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
    marginTop: 2,
  },
  triggerHint: {
    color: '#475569',
    fontSize: 11,
    marginTop: 2,
    fontStyle: 'italic',
  },
  actionCol: {
    alignItems: 'center',
    justifyContent: 'space-between',
    height: 48,
  },
  callActionButton: {
    backgroundColor: 'rgba(16, 185, 129, 0.2)',
    borderWidth: 1,
    borderColor: '#10B981',
    paddingHorizontal: 12,
    paddingVertical: 5,
    borderRadius: 6,
  },
  callActionText: {
    color: '#34D399',
    fontSize: 10,
    fontWeight: '800',
  },
  deleteButton: {
    padding: 4,
  },
  deleteText: {
    color: '#64748B',
    fontSize: 12,
  },
});
