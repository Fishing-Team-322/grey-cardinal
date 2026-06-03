/**
 * Minimal type stubs for @tauri-apps/api so the project typechecks
 * even before `npm install` is run (or when the registry is unreachable).
 * The actual package must be installed for runtime use inside Tauri.
 */
declare module "@tauri-apps/api/core" {
  export function invoke<T>(
    cmd: string,
    args?: Record<string, unknown>
  ): Promise<T>;
}
