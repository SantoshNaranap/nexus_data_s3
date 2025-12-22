/// <reference types="vite/client" />
import axios from 'axios';
import type { DataSource, ChatRequest, ChatResponse, AgentStep, User, SourceReference } from '../types';

// Centralized API base URL - single source of truth
export const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true,
  timeout: 10000, // 10 second timeout
});

export const datasourceApi = {
  list: async (): Promise<DataSource[]> => {
    const response = await api.get<DataSource[]>('/api/datasources');
    return response.data;
  },

  test: async (datasourceId: string): Promise<{ connected: boolean; error?: string }> => {
    const response = await api.post(`/api/datasources/${datasourceId}/test`);
    return response.data;
  },
};

export const credentialsApi = {
  checkStatus: async (datasource: string): Promise<{ configured: boolean }> => {
    const response = await api.get(`/api/credentials/${datasource}/status`);
    return response.data;
  },

  save: async (datasource: string, credentials: Record<string, string>) => {
    const response = await api.post('/api/credentials', {
      datasource,
      credentials,
    });
    return response.data;
  },

  delete: async (datasource: string) => {
    await api.delete(`/api/credentials/${datasource}`);
  },
};

export const chatApi = {
  sendMessage: async (request: ChatRequest): Promise<ChatResponse> => {
    const response = await api.post<ChatResponse>('/api/chat/message', request);
    return response.data;
  },

  sendMessageStream: async (
    request: ChatRequest,
    onChunk: (chunk: string) => void,
    onSession: (sessionId: string) => void,
    onDone: (metadata?: { sources?: SourceReference[]; followUpQuestions?: string[] }) => void,
    onError: (error: string) => void,
    onAgentStep?: (step: AgentStep) => void,
    onSource?: (source: SourceReference) => void,
    onThinking?: (content: string) => void,
    onThinkingStart?: () => void,
    onThinkingEnd?: () => void,
    abortSignal?: AbortSignal
  ): Promise<void> => {
    const response = await fetch(`${API_BASE_URL}/api/chat/message/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include',
      body: JSON.stringify(request),
      signal: abortSignal,
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const reader = response.body?.getReader();
    const decoder = new TextDecoder();

    if (!reader) {
      throw new Error('No response body');
    }

    try {
      while (true) {
        const { done, value } = await reader.read();

        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));

              switch (data.type) {
                case 'session':
                  onSession(data.session_id);
                  break;
                case 'content':
                  onChunk(data.content);
                  break;
                case 'thinking_start':
                  if (onThinkingStart) {
                    onThinkingStart();
                  }
                  break;
                case 'thinking':
                  if (onThinking) {
                    onThinking(data.content);
                  }
                  break;
                case 'thinking_end':
                  if (onThinkingEnd) {
                    onThinkingEnd();
                  }
                  break;
                case 'agent_step':
                  if (onAgentStep) {
                    onAgentStep(data.step);
                  }
                  break;
                case 'source':
                  if (onSource) {
                    onSource(data.source);
                  }
                  break;
                case 'done':
                  onDone({
                    sources: data.sources,
                    followUpQuestions: data.follow_up_questions,
                  });
                  break;
                case 'error':
                  onError(data.error);
                  break;
              }
            } catch (parseError) {
              // Ignore parse errors for partial JSON
              console.debug('Skipping malformed SSE line:', line);
            }
          }
        }
      }
    } finally {
      reader.releaseLock();
    }
  },

  listSessions: async (): Promise<string[]> => {
    const response = await api.get<string[]>('/api/chat/sessions');
    return response.data;
  },

  createSession: async (datasource: string, name?: string) => {
    const response = await api.post('/api/chat/sessions', { datasource, name });
    return response.data;
  },

  deleteSession: async (sessionId: string) => {
    await api.delete(`/api/chat/sessions/${sessionId}`);
  },
};

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface SignupCredentials {
  email: string;
  password: string;
  name?: string;
}

export interface AuthResponse {
  message: string;
  user: User;
}

export const authApi = {
  getCurrentUser: async (): Promise<User | null> => {
    try {
      const response = await api.get<User>('/api/auth/me');
      return response.data;
    } catch (error) {
      // 401 means not authenticated, return null
      return null;
    }
  },

  login: async (credentials: LoginCredentials): Promise<AuthResponse> => {
    const response = await api.post<AuthResponse>('/api/auth/login', credentials);
    return response.data;
  },

  signup: async (credentials: SignupCredentials): Promise<AuthResponse> => {
    const response = await api.post<AuthResponse>('/api/auth/signup', credentials);
    return response.data;
  },

  logout: async (): Promise<void> => {
    await api.post('/api/auth/logout');
  },
};

// Digest API types
export interface DigestRequest {
  since?: string;  // ISO timestamp
  sources?: string[];
}

export interface SourceResult {
  datasource: string;
  success: boolean;
  data?: { response?: string };
  summary?: string;
  error?: string;
  tools_called?: string[];
  execution_time_ms?: number;
  timestamp?: string;
}

export interface DigestResponse {
  since: string | null;
  results: SourceResult[];
  summary: string;
  successful_sources: string[];
  failed_sources: string[];
  total_time_ms: number;
}

export interface LastLoginInfo {
  last_login: string | null;
  previous_login: string | null;
  has_previous_login: boolean;
}

export const digestApi = {
  getDigest: async (request?: DigestRequest): Promise<DigestResponse> => {
    // Digest queries multiple sources and calls Claude for each, so needs longer timeout
    const response = await api.post<DigestResponse>('/api/digest/what-you-missed', request || {}, {
      timeout: 120000, // 2 minute timeout for digest
    });
    return response.data;
  },

  getSources: async (): Promise<string[]> => {
    const response = await api.get<{ sources: string[] }>('/api/digest/sources');
    return response.data.sources;
  },

  getLastLogin: async (): Promise<LastLoginInfo> => {
    const response = await api.get<LastLoginInfo>('/api/digest/last-login');
    return response.data;
  },
};

export default api;
