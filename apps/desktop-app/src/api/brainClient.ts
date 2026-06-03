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

export type MeetingParticipant = {
  id: string;
  meeting_id: string;
  user_id: string;
  display_name?: string | null;
  device_id?: string | null;
  client_session_id?: string | null;
  status: "joined" | "left" | "disconnected";
  joined_at: string;
  left_at?: string | null;
  last_seen_at?: string | null;
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

export type DesktopProposal = {
  proposal_id: string;
  confirmation_id: string | null;
  title: string;
  description?: string | null;
  assignee_text?: string | null;
  priority: string;
  raw_text: string;
  source: string;
  created_at?: string | null;
};

export type DesktopTranscriptItem = {
  id: string;
  meeting_id: string;
  text: string;
  asr_provider?: string | null;
  created_at?: string | null;
};

export class BrainClient {
  constructor(
    private readonly baseUrl: string,
    private readonly internalToken: string
  ) {}

  async registerDevice(input: RegisterDeviceInput): Promise<DesktopIdentity> {
    return this.post("/desktop/devices/register", input);
  }

  async startSession(identity: DesktopIdentity): Promise<{ client_session_id: string; status: string }> {
    return this.post(
      "/desktop/sessions/start",
      {
        user_id: identity.user_id,
        device_id: identity.device_id,
        workspace_id: identity.workspace_id ?? null
      },
      identity
    );
  }

  async joinMeeting(identity: DesktopIdentity, meetingId: string): Promise<MeetingParticipant> {
    return this.post(
      `/desktop/meetings/${encodeURIComponent(meetingId)}/join`,
      { display_name: identity.display_name, metadata: { app: "desktop-app", version: "0.1.0" } },
      identity
    );
  }

  async leaveMeeting(identity: DesktopIdentity, meetingId: string): Promise<MeetingParticipant> {
    return this.post(
      `/desktop/meetings/${encodeURIComponent(meetingId)}/leave`,
      { reason: "desktop_app_leave" },
      identity
    );
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
        workspace_id: identity.workspace_id ?? null,
        source: {
          kind: "desktop_app",
          user_id: identity.user_id,
          device_id: identity.device_id,
          client_session_id: identity.client_session_id,
          microphone_id: "mock_microphone",
          capture_mode: "microphone",
          platform: "windows",
          app_version: "0.1.0"
        },
        speaker: {
          resolved_user_id: identity.user_id,
          resolved_name: identity.display_name,
          identity_source: "authenticated_client",
          identity_confidence: 1.0
        },
        text,
        is_final: true,
        asr: {
          provider: "mock",
          confidence: 1.0
        },
        audio: {
          source: "microphone",
          duration_ms: 3200
        },
        raw: { ui_manual_send: true }
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

  async listProposals(identity: DesktopIdentity): Promise<{ items: DesktopProposal[] }> {
    return this.get("/desktop/proposals", identity);
  }

  async confirmProposal(
    identity: DesktopIdentity,
    proposalId: string
  ): Promise<{ ok: boolean; task_public_id?: string | null; message: string }> {
    return this.post(`/desktop/proposals/${encodeURIComponent(proposalId)}/confirm`, {}, identity);
  }

  async rejectProposal(
    identity: DesktopIdentity,
    proposalId: string
  ): Promise<{ ok: boolean; message: string }> {
    return this.post(`/desktop/proposals/${encodeURIComponent(proposalId)}/reject`, {}, identity);
  }

  async recentTranscripts(identity: DesktopIdentity, limit = 10): Promise<{ items: DesktopTranscriptItem[] }> {
    return this.get(`/desktop/transcripts/recent?limit=${limit}`, identity);
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
