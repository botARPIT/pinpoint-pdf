import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { FileUploader } from '@/components/FileUploader';
import { MessageList } from '@/components/chat/MessageList';
import { ChatInput } from '@/components/chat/ChatInput';
import api from '@/lib/api';
import type { Message } from '@/lib/types';
import { Loader2, Sparkles } from 'lucide-react';

export default function ChatPage() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const [docId, setDocId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [initializing] = useState(false);
  const [docReady, setDocReady] = useState(false);

  useEffect(() => {
    if (sessionId) {
      setLoading(true);
      api.get(`/sessions/${sessionId}`)
        .then(response => {
          setDocId(response.data.doc_id);
          setDocReady(true);
          const loadedMessages: Message[] = response.data.messages.map((msg: any) => ({
            id: msg.message_id,
            role: msg.role,
            content: msg.content,
            created_at: msg.created_at,
            sources: msg.sources,
          }));
          setMessages(loadedMessages);
        })
        .catch(err => console.error('Failed to load session', err))
        .finally(() => setLoading(false));
    }
  }, [sessionId]);

  useEffect(() => {
    if (!docId || docReady) return;
    const pollInterval = setInterval(async () => {
      try {
        const response = await api.get('/documents');
        const doc = response.data.documents.find((d: any) => d.doc_id === docId);
        if (doc?.status === 'ready') {
          setDocReady(true);
          clearInterval(pollInterval);
        } else if (doc?.status === 'failed') {
          setMessages(prev => [...prev, {
            id: 'error-processing',
            role: 'assistant',
            content: `Document processing failed: ${doc.error_message || 'Unknown error'}. Please try uploading again.`,
          }]);
          clearInterval(pollInterval);
        }
      } catch (err) { console.error('Polling error', err); }
    }, 3000);
    return () => clearInterval(pollInterval);
  }, [docId, docReady]);

  const handleUploadComplete = (newDocId: string, filename: string) => {
    setDocId(newDocId);
    setDocReady(false);
    setMessages([{
      id: 'init',
      role: 'assistant',
      content: `"${filename}" uploaded! Processing your document — ask me anything once it's ready.`
    }]);
  };

  const handleSendMessage = async (text: string) => {
    if (!docId) return;
    if (!docReady) {
      setMessages(prev => [...prev, {
        id: Date.now().toString() + '-wait',
        role: 'assistant',
        content: 'Your document is still being processed. Please wait a moment and try again.',
      }]);
      return;
    }
    const newMessage: Message = { id: Date.now().toString(), role: 'user', content: text };
    setMessages(prev => [...prev, newMessage]);
    setLoading(true);
    try {
      const payload = { doc_id: docId, question: text, session_id: sessionId || undefined };
      const response = await api.post('/chat', payload);
      if (!sessionId && response.data.session_id) {
        navigate(`/chat/${response.data.session_id}`, { replace: true });
      }
      setMessages(prev => [...prev, {
        id: Date.now().toString() + '-bot',
        role: 'assistant',
        content: response.data.answer,
        sources: response.data.sources,
        latency_ms: response.data.latency_ms,
      }]);
    } catch (error: any) {
      const errorMsg = error.response?.status === 409
        ? 'Your document is still being processed. Please wait a moment and try again.'
        : 'Sorry, I encountered an error processing your request.';
      setMessages(prev => [...prev, { id: Date.now().toString() + '-error', role: 'assistant', content: errorMsg }]);
    } finally {
      setLoading(false);
    }
  };

  if (initializing) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="animate-spin" style={{ color: '#fb7185' }} />
      </div>
    );
  }

  // Empty state — no doc, no session
  if (!docId && !sessionId) {
    return (
      <div className="relative flex flex-col items-center justify-center h-full overflow-hidden" style={{ minHeight: '100vh' }}>
        {/* Background orbs */}
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[500px] h-[500px] rounded-full orb-animate" style={{
            background: 'radial-gradient(circle, rgba(244,63,94,0.15) 0%, transparent 70%)',
            filter: 'blur(60px)'
          }} />
          <div className="absolute bottom-1/4 left-1/4 w-64 h-64 rounded-full orb-animate" style={{
            background: 'radial-gradient(circle, rgba(251,113,133,0.1) 0%, transparent 70%)',
            filter: 'blur(40px)',
            animationDelay: '3s'
          }} />
        </div>

        <div className="relative z-10 flex flex-col items-center text-center px-8 space-y-10 animate-fade-in">
          <div className="space-y-3">
            <div className="flex items-center justify-center gap-2 mb-4">
              <Sparkles className="w-5 h-5" style={{ color: '#fb7185' }} />
              <span className="text-sm font-semibold uppercase tracking-widest" style={{ color: '#fb7185' }}>
                AI-powered PDF chat
              </span>
            </div>
            <h1 className="text-5xl font-bold leading-tight text-white">
              Ask anything about<br />
              <span className="gradient-text">your documents</span>
            </h1>
            <p className="text-lg max-w-md" style={{ color: 'rgba(255,255,255,0.4)' }}>
              Upload a PDF and start a conversation. Get precise answers with source citations.
            </p>
          </div>

          <FileUploader onUploadComplete={handleUploadComplete} />
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen" style={{ background: '#0a0812' }}>
      {/* Processing banner */}
      {!docReady && docId && (
        <div className="flex items-center justify-center gap-2 px-4 py-2.5 flex-none" style={{
          background: 'linear-gradient(90deg, rgba(244,63,94,0.1), rgba(251,113,133,0.05), rgba(244,63,94,0.1))',
          borderBottom: '1px solid rgba(244,63,94,0.15)'
        }}>
          <Loader2 className="h-3.5 w-3.5 animate-spin" style={{ color: '#fb7185' }} />
          <span className="text-xs font-medium" style={{ color: '#fb7185' }}>
            Processing your document — you can ask questions once it's ready
          </span>
        </div>
      )}

      <MessageList messages={messages} isLoading={loading} />
      <ChatInput onSend={handleSendMessage} disabled={loading} />
    </div>
  );
}
