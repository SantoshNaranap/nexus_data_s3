import axios from 'axios';
import type { DataSource, ChatRequest, ChatResponse } from '../types';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const datasourceApi = {
  list: async (): Promise<DataSource[]> => {
    const response = await api.get<DataSource[]>('/api/datasources');
    return response.data;
  },

  test: async (datasourceId: string) => {
    const response = await api.get(`/api/datasources/${datasourceId}/test`);
    return response.data;
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
    onDone: () => void,
    onError: (error: string) => void
  ): Promise<void> => {
    const response = await fetch(`${API_BASE_URL}/api/chat/message/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
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
            const data = JSON.parse(line.slice(6));

            switch (data.type) {
              case 'session':
                onSession(data.session_id);
                break;
              case 'content':
                onChunk(data.content);
                break;
              case 'done':
                onDone();
                break;
              case 'error':
                onError(data.error);
                break;
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

export default api;
