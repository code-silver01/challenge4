const API_BASE = 'http://127.0.0.1:8000/api';

export interface SessionConfig {
  role: 'fan' | 'volunteer' | 'organizer';
  language: string;
  accessibility_needs: string[];
  ticket_zone?: string;
}

export interface Session {
  session_id: string;
  role: string;
  language: string;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  data?: any;
}

export const api = {
  async createSession(config: SessionConfig): Promise<Session> {
    const res = await fetch(`${API_BASE}/session`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    });
    if (!res.ok) throw new Error('Failed to create session');
    return res.json();
  },

  async sendMessage(sessionId: string, message: string): Promise<any> {
    const res = await fetch(`${API_BASE}/chat?session_id=${sessionId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, message }),
    });
    if (!res.ok) throw new Error('Failed to send message');
    return res.json();
  },

  async getCrowdStatus(): Promise<any> {
    const res = await fetch(`${API_BASE}/crowd/status`);
    if (!res.ok) throw new Error('Failed to get crowd status');
    return res.json();
  },

  async getWellbeingAlerts(sessionId: string): Promise<any> {
    const res = await fetch(`${API_BASE}/wellbeing/alerts?session_id=${sessionId}`);
    if (!res.ok) throw new Error('Failed to get wellbeing alerts');
    return res.json();
  },

  async draftAnnouncement(sessionId: string, note: string, priority: string): Promise<any> {
    const res = await fetch(`${API_BASE}/announcements/draft?session_id=${sessionId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ situation_note: note, priority }),
    });
    if (!res.ok) throw new Error('Failed to draft announcement');
    return res.json();
  }
};
