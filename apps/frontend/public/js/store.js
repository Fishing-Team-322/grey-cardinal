export function createStore(initial) {
  const subscribers = new Set();
  const target = { ...initial };
  const state = new Proxy(target, {
    set(object, key, value) {
      object[key] = value;
      subscribers.forEach((callback) => callback(key, value));
      return true;
    },
  });
  return {
    state,
    subscribe(callback) {
      subscribers.add(callback);
      return () => subscribers.delete(callback);
    },
  };
}

export const appStore = createStore({
  currentUser: null,
  context: null,
  selectedTeamId: null,
});
