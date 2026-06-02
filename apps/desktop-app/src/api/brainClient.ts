export type DesktopIdentity = {
  user_id: string;
  device_id: string;
  client_session_id: string;
  workspace_id?: string | null;
  display_name: string;
};

export type RegisterDeviceInput = {
  display_name: string;
  telegram_username?: string;
  device_name: string;
  platform: "windows" | "linux" | "macos";
  app_version?: string;
};

export type DesktopTask = {
  id: string;
  public_id: string;
  title: string;
  status: string;
  assignee_text?: string | null;
};

export type GamificationState = {
  user_id: string;
  points_total: number;
  level: number;
  recent_events: Array<{ kind: string; points: number; reason: string }>;
};

export class BrainClient {
  constructor(
    private readonly baseUrl: string,
    private readonly internalToken: string
  ) {}

  async registerDevice(input: RegisterDeviceInput): Promise<DesktopIdentity> {
    return this.post("/desktop/devices/register", input);
  }

  async joinMeeting(identity: DesktopIdentity, meetingId: string): Promise<unknown> {
    return this.post(`/desktop/meetings/${encodeURIComponent(meetingId)}/join`, {}, identity);
  }

  async heartbeat(identity: DesktopIdentity, meetingId?: string): Promise<unknown> {
    return this.post("/desktop/heartbeat", { meeting_public_id: meetingId ?? null }, identity);
  }

  async sendMockTranscript(
    identity: DesktopIdentity,
    meetingId: string,
    text: string
  ): Promise<unknown> {
    return this.post(
      "/desktop/transcripts",
      {
        meeting_id: meetingId,
        text,
        is_final: true,
        microphone_id: "mock_microphone",
        capture_mode: "microphone",
        asr_provider: "mock",
        asr_confidence: 0.91,
        vad_confidence: 0.88,
        duration_ms: 3200
      },
      identity
    );
  }

  async listTasks(identity: DesktopIdentity): Promise<{ tasks: DesktopTask[] }> {
    return this.get("/desktop/tasks", identity);
  }

  async gamification(identity: DesktopIdentity): Promise<GamificationState> {
    return this.get("/desktop/gamification/me", identity);
  }

  private async get<T>(path: string, identity?: DesktopIdentity): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      headers: this.headers(identity)
    });
    return this.parse<T>(response);
  }

  private async post<T>(path: string, body: unknown, identity?: DesktopIdentity): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      method: "POST",
      headers: {
        ...this.headers(identity),
        "Content-Type": "application/json"
      },
      body: JSON.stringify(body)
    });
    return this.parse<T>(response);
  }

  private headers(identity?: DesktopIdentity): Record<string, string> {
    const headers: Record<string, string> = {
      "X-Internal-Token": this.internalToken
    };
    if (identity) {
      headers["X-GC-User-Id"] = identity.user_id;
      headers["X-GC-Device-Id"] = identity.device_id;
      headers["X-GC-Client-Session-Id"] = identity.client_session_id;
    }
    return headers;
  }

  private async parse<T>(response: Response): Promise<T> {
    if (!response.ok) {
      throw new Error(`${response.status} ${await response.text()}`);
    }
    return response.json() as Promise<T>;
  }
}
