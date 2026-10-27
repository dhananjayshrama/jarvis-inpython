export interface Contact {
  id: string;
  name: string;
  phone: string;
  relationship?: string;
  avatarColor?: string;
}

export const DEFAULT_CONTACTS: Contact[] = [
  {
    id: '1',
    name: 'Mom',
    phone: '+917875030173',
    relationship: 'Mother',
    avatarColor: '#EC4899',
  },
  {
    id: '2',
    name: 'Ronya BIGCE',
    phone: '+919158220533',
    relationship: 'Friend',
    avatarColor: '#3B82F6',
  },
  {
    id: '3',
    name: 'Dad',
    phone: '+919811122233',
    relationship: 'Father',
    avatarColor: '#10B981',
  },
  {
    id: '4',
    name: 'Emergency',
    phone: '112',
    relationship: 'Services',
    avatarColor: '#EF4444',
  },

  {
    id: '6',
    name: 'Padyy brother',
    phone: '+919767393085',
    relationship: 'bother',
    avatarColor: '#F59E0B',
  },
  {
    id: '7',
    name: 'Sai',
    phone: '+919561566971',
    relationship: 'sai',
    avatarColor: '#F58E0B',
  },
];

let inMemoryContacts: Contact[] = [...DEFAULT_CONTACTS];

export function getContacts(): Contact[] {
  return inMemoryContacts;
}

export function saveContacts(contacts: Contact[]): void {
  inMemoryContacts = contacts;
}

export function addContact(name: string, phone: string, relationship?: string): Contact {
  const newContact: Contact = {
    id: Date.now().toString(),
    name: name.trim(),
    phone: phone.trim(),
    relationship: relationship?.trim() || 'Contact',
    avatarColor: ['#3B82F6', '#8B5CF6', '#10B981', '#F59E0B', '#EC4899'][Math.floor(Math.random() * 5)],
  };
  inMemoryContacts.push(newContact);
  return newContact;
}

export function deleteContact(id: string): void {
  inMemoryContacts = inMemoryContacts.filter(c => c.id !== id);
}

export function resolveTargetToPhoneNumber(target: string): { contactName: string; phoneNumber: string } | null {
  const query = target.toLowerCase().trim().replace(/^(my|the|contact)\s+/, '');

  const numericOnly = target.replace(/[^0-9+]/g, '');
  if (numericOnly.length >= 3 && /^[+]?[0-9]{3,}$/.test(numericOnly)) {
    return { contactName: target, phoneNumber: numericOnly };
  }

  const exactMatch = inMemoryContacts.find(
    c => c.name.toLowerCase() === query || c.relationship?.toLowerCase() === query
  );
  if (exactMatch) {
    return { contactName: exactMatch.name, phoneNumber: exactMatch.phone };
  }

  const partialMatch = inMemoryContacts.find(
    c => c.name.toLowerCase().includes(query) || query.includes(c.name.toLowerCase())
  );
  if (partialMatch) {
    return { contactName: partialMatch.name, phoneNumber: partialMatch.phone };
  }

  return null;
}
