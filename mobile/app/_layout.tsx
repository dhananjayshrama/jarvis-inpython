import React from 'react';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { View, StyleSheet } from 'react-native';

export default function RootLayout() {
  return (
    <View style={styles.container}>
      <StatusBar style="light" />
      <Stack
        screenOptions={{
          headerStyle: {
            backgroundColor: '#090D16',
          },
          headerTintColor: '#38BDF8',
          headerTitleStyle: {
            fontWeight: '700',
            letterSpacing: 2,
          },
          contentStyle: {
            backgroundColor: '#040711',
          },
          animation: 'fade',
        }}
      >
        <Stack.Screen
          name="index"
          options={{
            headerShown: false,
          }}
        />
        <Stack.Screen
          name="contacts"
          options={{
            title: 'SPEED DIAL DIRECTORY',
            headerBackTitle: 'Back',
          }}
        />
        <Stack.Screen
          name="remote"
          options={{
            title: 'LAPTOP CONTROLLER',
            headerBackTitle: 'Back',
          }}
        />
      </Stack>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#040711',
  },
});
