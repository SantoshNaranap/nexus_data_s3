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
    onSource?: (source: SourceReference) => void
  ): Promise<void> => {
    const response = await fetch(`${API_BASE_URL}/api/chat/message/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include',
      body: JSON.stringify(request),
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

  logout: async (): Promise<void> => {
    await api.post('/api/auth/logout');
  },

  getGoogleAuthUrl: (): string => {
    return `${API_BASE_URL}/api/auth/google`;
  },
};

export default api;
