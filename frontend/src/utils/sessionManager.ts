/**
 * SessionManager - Manages chat session persistence using localStorage
 *
 * This ensures chat history persists across page refreshes by storing
 * session_id in localStorage per datasource.
 */

const SESSION_KEY_PREFIX = 'chat_session_';

interface SessionData {
  sessionId: string;
  datasource: string;
  createdAt: string;
  lastUsed: string;
}

export class SessionManager {
  /**
   * Get or create a session ID for a datasource
   */
  static getSessionId(datasource: string): string {
    const key = `${SESSION_KEY_PREFIX}${datasource}`;
    const stored = localStorage.getItem(key);

    if (stored) {
      try {
        const session: SessionData = JSON.parse(stored);

        // Update last used timestamp
        session.lastUsed = new Date().toISOString();
        localStorage.setItem(key, JSON.stringify(session));

        console.log(`[SessionManager] Reusing session ${session.sessionId} for ${datasource}`);
        return session.sessionId;
      } catch (error) {
        console.error('[SessionManager] Failed to parse stored session, creating new one', error);
      }
    }

    // Create new session
    const newSession: SessionData = {
      sessionId: crypto.randomUUID(),
      datasource,
      createdAt: new Date().toISOString(),
      lastUsed: new Date().toISOString(),
    };

    localStorage.setItem(key, JSON.stringify(newSession));
    console.log(`[SessionManager] Created new session ${newSession.sessionId} for ${datasource}`);
    return newSession.sessionId;
  }

  /**
   * Start a new session (clear history)
   */
  static startNewSession(datasource: string): string {
    const key = `${SESSION_KEY_PREFIX}${datasource}`;
    localStorage.removeItem(key);
    console.log(`[SessionManager] Cleared session for ${datasource}`);
    return this.getSessionId(datasource);
  }

  /**
   * Clear all sessions
   */
  static clearAllSessions(): void {
    const keys = Object.keys(localStorage);
    keys.forEach(key => {
      if (key.startsWith(SESSION_KEY_PREFIX)) {
        localStorage.removeItem(key);
      }
    });
    console.log('[SessionManager] Cleared all sessions');
  }

  /**
   * Get all active sessions
   */
  static getAllSessions(): SessionData[] {
    const keys = Object.keys(localStorage);
    return keys
      .filter(key => key.startsWith(SESSION_KEY_PREFIX))
      .map(key => {
        const data = localStorage.getItem(key);
        if (!data) return null;
        try {
          return JSON.parse(data) as SessionData;
        } catch {
          return null;
        }
      })
      .filter((session): session is SessionData => session !== null);
  }

  /**
   * Get session info for debugging
   */
  static getSessionInfo(datasource: string): SessionData | null {
    const key = `${SESSION_KEY_PREFIX}${datasource}`;
    const stored = localStorage.getItem(key);
    if (!stored) return null;

    try {
      return JSON.parse(stored);
    } catch {
      return null;
    }
  }
}
