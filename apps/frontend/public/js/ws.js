const subscribers = new Map();
let socket = null;
let reconnectTimer = null;
let shouldReconnect = true;

export function wsConnect() {
  if (socket && socket.readyState !== WebSocket.CLOSED) return socket;
  shouldReconnect = true;
  const scheme = location.protocol === "https:" ? "wss:" : "ws:";
  socket = new WebSocket(`${scheme}//${location.host}/ws/events`);
  socket.onmessage = (event) => {
    let message;
    try {
      message = JSON.parse(event.data);
    } catch {
      return;
    }
    subscribers.get(message.event)?.forEach((callback) => callback(message.payload));
  };
  socket.onclose = () => {
    socket = null;
    if (shouldReconnect) reconnectTimer = setTimeout(wsConnect, 2000);
  };
  socket.onerror = () => socket?.close();
  return socket;
}

export function wsOn(event, callback) {
  if (!subscribers.has(event)) subscribers.set(event, new Set());
  subscribers.get(event).add(callback);
  return () => subscribers.get(event)?.delete(callback);
}

export function wsClose() {
  shouldReconnect = false;
  clearTimeout(reconnectTimer);
  if (socket) {
    socket.onclose = null;
    socket.close();
    socket = null;
  }
}
