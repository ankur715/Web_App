import { StyleSheet } from 'react-native';
import { WebView } from 'react-native-webview';

// ngrok tunnel to the Mac running `python app.py` on port 8000.
// This URL changes every time the tunnel restarts (free ngrok plan) —
// update it here if `ngrok http 8000` prints a new address.
const BACKEND_URL = 'https://groggily-outing-unmixed.ngrok-free.dev';

export default function HomeScreen() {
  return (
    <WebView
      source={{
        uri: BACKEND_URL,
        headers: { 'ngrok-skip-browser-warning': 'true' },
      }}
      style={styles.container}
      startInLoadingState
    />
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
});
