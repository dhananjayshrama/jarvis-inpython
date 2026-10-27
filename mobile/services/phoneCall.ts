import { Linking, Platform, Alert } from 'react-native';

// Try importing RNImmediatePhoneCall if available in native build
let RNImmediatePhoneCall: any = null;
try {
  // @ts-ignore
  RNImmediatePhoneCall = require('react-native-immediate-phone-call')?.default || require('react-native-immediate-phone-call');
} catch (e) {
  RNImmediatePhoneCall = null;
}

export function cleanPhoneNumber(raw: string): string {
  return raw.replace(/[^0-9+]/g, '');
}

export async function makePhoneCall(phoneNumber: string, contactName?: string): Promise<boolean> {
  const cleaned = cleanPhoneNumber(phoneNumber);
  if (!cleaned) {
    Alert.alert('Invalid Number', `Cannot dial empty or invalid number: "${phoneNumber}"`);
    return false;
  }

  const displayName = contactName || cleaned;

  try {
    if (RNImmediatePhoneCall && typeof RNImmediatePhoneCall.immediatePhoneCall === 'function') {
      RNImmediatePhoneCall.immediatePhoneCall(cleaned);
      return true;
    }

    const url = `tel:${cleaned}`;
    const supported = await Linking.canOpenURL(url);
    if (supported) {
      await Linking.openURL(url);
      return true;
    } else {
      Alert.alert('Dialer Unavailable', `Your device cannot open telephone links for ${displayName}.`);
      return false;
    }
  } catch (error) {
    console.error('Failed to place phone call:', error);
    Alert.alert('Call Failed', `Could not place call to ${displayName}. Error: ${error}`);
    return false;
  }
}
