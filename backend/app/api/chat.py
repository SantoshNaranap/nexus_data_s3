"""Chat API routes."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from typing import List
import uuid
import json

from app.models.chat import ChatRequest, ChatResponse, SessionCreate, Session
from app.services.chat_service import chat_service

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/message", response_model=ChatResponse)
async def send_message(request: ChatRequest):
    """Send a chat message and get a response."""
    try:
        # Generate session ID if not provided
        session_id = request.session_id or str(uuid.uuid4())

        # Process message
        response_text, tool_calls = await chat_service.process_message(
            message=request.message,
            datasource=request.datasource,
            session_id=session_id,
        )

        return ChatResponse(
            message=response_text,
            session_id=session_id,
            datasource=request.datasource,
            tool_calls=tool_calls if tool_calls else None,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/message/stream")
async def send_message_stream(request: ChatRequest):
    """Send a chat message and get a streaming response."""
    try:
        # Generate session ID if not provided
        session_id = request.session_id or str(uuid.uuid4())

        async def event_generator():
            """Generate Server-Sent Events."""
            try:
                # Send session ID first
                yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"

                # Stream the response
                async for chunk in chat_service.process_message_stream(
                    message=request.message,
                    datasource=request.datasource,
                    session_id=session_id,
                ):
                    yield f"data: {json.dumps({'type': 'content', 'content': chunk})}\n\n"

                # Send done signal
                yield f"data: {json.dumps({'type': 'done'})}\n\n"

            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions", response_model=List[str])
async def list_sessions():
    """List all active chat sessions."""
    return list(chat_service.sessions.keys())


@router.post("/sessions", response_model=dict)
async def create_session(request: SessionCreate):
    """Create a new chat session."""
    session_id = str(uuid.uuid4())
    chat_service.sessions[session_id] = []

    return {
        "session_id": session_id,
        "datasource": request.datasource,
        "name": request.name,
    }


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a chat session."""
    if session_id in chat_service.sessions:
        del chat_service.sessions[session_id]
        return {"message": "Session deleted"}

    raise HTTPException(status_code=404, detail="Session not found")
