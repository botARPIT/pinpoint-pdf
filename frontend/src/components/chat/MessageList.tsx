import { useEffect, useRef } from 'react';
import { cn } from '@/lib/utils';
import { Bot, User, BookOpen } from 'lucide-react';
import type { Message, Source } from '@/lib/types';
import { useState } from 'react';

export type { Message, Source };

interface MessageListProps {
  messages: Message[];
  isLoading?: boolean;
}

function TypingIndicator() {
  return (
    <div className="flex items-start gap-3 animate-slide-up">
      <div className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0" style={{
        background: 'rgba(244,63,94,0.15)',
        border: '1px solid rgba(244,63,94,0.2)'
      }}>
        <Bot className="w-4 h-4" style={{ color: '#fb7185' }} />
      </div>
      <div className="px-4 py-3 rounded-2xl rounded-tl-sm" style={{
        background: 'rgba(255,255,255,0.05)',
        border: '1px solid rgba(255,255,255,0.06)'
      }}>
        <div className="flex gap-1 items-center h-4">
          {[0, 1, 2].map((i) => (
            <span key={i} className="w-1.5 h-1.5 rounded-full animate-pulse-dot" style={{
              background: '#fb7185',
              animationDelay: `${i * 0.16}s`
            }} />
          ))}
        </div>
      </div>
    </div>
  );
}

function SourcesPanel({ sources, latency_ms }: { sources: Source[]; latency_ms?: number }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-2">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-xs transition-colors"
        style={{ color: open ? '#fb7185' : 'rgba(255,255,255,0.3)' }}
      >
        <BookOpen className="w-3 h-3" />
        <span>{sources.length} source{sources.length !== 1 ? 's' : ''}</span>
        {latency_ms && (
          <span className="ml-2" style={{ color: 'rgba(255,255,255,0.2)' }}>{latency_ms}ms</span>
        )}
        <span className="ml-1">{open ? '↑' : '↓'}</span>
      </button>
      {open && (
        <div className="mt-2 space-y-1.5 animate-slide-up">
          {sources.map((source, idx) => (
            <div key={idx} className="flex items-center gap-2 px-3 py-2 rounded-xl text-xs" style={{
              background: 'rgba(244,63,94,0.08)',
              border: '1px solid rgba(244,63,94,0.15)'
            }}>
              <span className="font-bold text-rose-400 flex-shrink-0">p.{source.page}</span>
              <span className="truncate" style={{ color: 'rgba(255,255,255,0.5)' }}>{source.section || 'Untitled section'}</span>
              {source.relevance_score && (
                <span className="ml-auto flex-shrink-0 font-medium" style={{ color: '#fb7185' }}>
                  {Math.round(source.relevance_score * 100)}%
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function MessageList({ messages, isLoading }: MessageListProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6">
      {messages.map((message, i) => (
        <div
          key={message.id}
          className={cn('flex items-start gap-3 animate-slide-up', message.role === 'user' ? 'flex-row-reverse' : 'flex-row')}
          style={{ animationDelay: `${i * 30}ms` }}
        >
          {/* Avatar */}
          <div className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0" style={
            message.role === 'user'
              ? { background: 'linear-gradient(135deg, #fb7185, #e11d48)' }
              : { background: 'rgba(244,63,94,0.15)', border: '1px solid rgba(244,63,94,0.2)' }
          }>
            {message.role === 'user'
              ? <User className="w-4 h-4 text-white" />
              : <Bot className="w-4 h-4" style={{ color: '#fb7185' }} />
            }
          </div>

          {/* Bubble */}
          <div className={cn('flex flex-col gap-1 max-w-[75%]', message.role === 'user' ? 'items-end' : 'items-start')}>
            <div
              className="px-4 py-3 text-sm leading-relaxed"
              style={message.role === 'user' ? {
                background: 'linear-gradient(135deg, rgba(244,63,94,0.8) 0%, rgba(225,29,72,0.85) 100%)',
                borderRadius: '18px 18px 4px 18px',
                color: 'white'
              } : {
                background: 'rgba(255,255,255,0.05)',
                border: '1px solid rgba(255,255,255,0.06)',
                borderRadius: '18px 18px 18px 4px',
                color: 'rgba(255,255,255,0.85)'
              }}
            >
              {message.content}
            </div>

            {message.role === 'assistant' && message.sources && message.sources.length > 0 && (
              <SourcesPanel sources={message.sources} latency_ms={message.latency_ms} />
            )}
          </div>
        </div>
      ))}

      {isLoading && <TypingIndicator />}
      <div ref={scrollRef} />
    </div>
  );
}
