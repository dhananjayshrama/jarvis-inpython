cdexport type ConnectionStatus = 'DISCONNECTED' | 'CONNECTING' | 'CONNECTED';

export interface JarvisMessage {
  type: string;
  [key: string]: any;
}

type StatusCallback = (status: ConnectionStatus) => void;
type MessageCallback = (message: JarvisMessage) => void;
type CallRequestCallback = (target: string, raw?: string) => void;

class JarvisSocketService {
  private socket: WebSocket | null = null;
  private currentIp: string = '';
  private status: ConnectionStatus = 'DISCONNECTED';
  private shouldReconnect: boolean = false;
  private reconnectTimer: any = null;

  private statusListeners: Set<StatusCallback> = new Set();
  private messageListeners: Set<MessageCallback> = new Set();
  private callListeners: Set<CallRequestCallback> = new Set();

  public getStatus(): ConnectionStatus {
    return this.status;
  }

  public getIp(): string {
    return this.currentIp;
  }

  public onStatusChange(callback: StatusCallback): () => void {
    this.statusListeners.add(callback);
    callback(this.status);
    return () => this.statusListeners.delete(callback);
  }

  public onMessage(callback: MessageCallback): () => void {
    this.messageListeners.add(callback);
    return () => this.messageListeners.delete(callback);
  }

  public onCallRequest(callback: CallRequestCallback): () => void {
    this.callListeners.add(callback);
    return () => this.callListeners.delete(callback);
  }

  private setStatus(status: ConnectionStatus) {
    this.status = status;
    this.statusListeners.forEach(cb => cb(status));
  }

  public connect(ipAddress: string): void {
    if (!ipAddress) return;

    let host = ipAddress.trim();
    if (!host.startsWith('ws://') && !host.startsWith('wss://')) {
      if (!host.includes(':')) {
        host = `ws://${host}:8765`;
      } else {
        host = `ws://${host}`;
      }
    }

    this.currentIp = ipAddress.trim();
    this.shouldReconnect = true;
    this.cleanup();

    this.setStatus('CONNECTING');
    console.log(`[JARVIS Socket] Connecting to ${host}...`);

    try {
      this.socket = new WebSocket(host);

      this.socket.onopen = () => {
        console.log(`[JARVIS Socket] Connected to ${host}`);
        this.setStatus('CONNECTED');
        this.send({
          type: 'MOBILE_CLIENT_HELLO',
          platform: 'Expo React Native',
          device: 'Dhananjay Mobile',
        });
      };

      this.socket.onmessage = (event) => {
        try {
          const data: JarvisMessage = JSON.parse(event.data);
          console.log('[JARVIS Socket] Message received:', data);

          if (data.type === 'CALL_REQUEST') {
            const target = data.target || '';
            this.callListeners.forEach(cb => cb(target, data.raw));
          }

          this.messageListeners.forEach(cb => cb(data));
        } catch (e) {
          console.warn('[JARVIS Socket] Non-JSON message received:', event.data);
        }
      };

      this.socket.onerror = (err) => {
        console.warn('[JARVIS Socket] Connection error:', err);
      };

      this.socket.onclose = (e) => {
        console.log(`[JARVIS Socket] Connection closed (code: ${e.code})`);
        this.setStatus('DISCONNECTED');
        if (this.shouldReconnect) {
          this.scheduleReconnect();
        }
      };
    } catch (err) {
      console.error('[JARVIS Socket] Failed to create WebSocket:', err);
      this.setStatus('DISCONNECTED');
    }
  }

  private scheduleReconnect() {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.reconnectTimer = setTimeout(() => {
      if (this.shouldReconnect && this.currentIp && this.status === 'DISCONNECTED') {
        console.log('[JARVIS Socket] Attempting auto-reconnect...');
        this.connect(this.currentIp);
      }
    }, 4000);
  }

  public disconnect(): void {
    this.shouldReconnect = false;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.cleanup();
    this.setStatus('DISCONNECTED');
  }

  private cleanup(): void {
    if (this.socket) {
      this.socket.onopen = null;
      this.socket.onmessage = null;
      this.socket.onerror = null;
      this.socket.onclose = null;
      try {
        this.socket.close();
      } catch (e) {}
      this.socket = null;
    }
  }

  public send(payload: JarvisMessage): boolean {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(payload));
      return true;
    }
    return false;
  }

  public sendCommandToLaptop(command: string): boolean {
    return this.send({
      type: 'EXECUTE_COMMAND',
      command: command.trim(),
      timestamp: Date.now(),
    });
  }
}

export const jarvisSocket = new JarvisSocketService();
