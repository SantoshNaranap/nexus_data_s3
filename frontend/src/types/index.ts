export interface DataSource {
  id: string;
  name: string;
  description: string;
  icon: string;
  enabled: boolean;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp?: string;
}

export interface ChatRequest {
  message: string;
  datasource: string;
  session_id?: string;
}

export interface ChatResponse {
  message: string;
  session_id: string;
  datasource: string;
  tool_calls?: Array<{
    name: string;
    arguments: Record<string, unknown>;
    result: string;
  }>;
}
