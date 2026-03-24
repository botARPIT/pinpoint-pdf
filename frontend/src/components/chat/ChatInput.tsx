import { useState, useRef, useEffect } from 'react';
import { ArrowUp, Loader2 } from 'lucide-react';

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
}

export function ChatInput({ onSend, disabled }: ChatInputProps) {
  const [input, setInput] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [focused, setFocused] = useState(false);

  const handleSend = () => {
    if (input.trim() && !disabled) {
      onSend(input);
      setInput('');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 160)}px`;
    }
  }, [input]);

  const canSend = input.trim() && !disabled;

  return (
    <div className="px-4 pb-4 pt-2 flex-none">
      <div
        className="flex items-end gap-3 px-4 py-3 rounded-2xl transition-all duration-200"
        style={{
          background: 'rgba(255,255,255,0.05)',
          border: `1px solid ${focused ? 'rgba(244,63,94,0.4)' : 'rgba(255,255,255,0.08)'}`,
          boxShadow: focused ? '0 0 0 3px rgba(244,63,94,0.1), 0 4px 24px rgba(244,63,94,0.08)' : 'none'
        }}
      >
        <textarea
          ref={textareaRef}
          className="flex-1 bg-transparent text-sm resize-none focus:outline-none placeholder:text-white/25"
          style={{
            color: 'rgba(255,255,255,0.85)',
            minHeight: '24px',
            maxHeight: '160px',
            lineHeight: '1.6'
          }}
          placeholder="Ask a question about your document…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          disabled={disabled}
          rows={1}
        />

        <button
          onClick={handleSend}
          disabled={!canSend}
          className="w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 transition-all duration-200"
          style={canSend ? {
            background: 'linear-gradient(135deg, #fb7185, #e11d48)',
            boxShadow: '0 4px 12px rgba(244,63,94,0.35)',
            transform: 'scale(1)'
          } : {
            background: 'rgba(255,255,255,0.07)',
            cursor: 'not-allowed'
          }}
          onMouseEnter={(e) => {
            if (canSend) (e.currentTarget as HTMLElement).style.transform = 'scale(1.05)';
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLElement).style.transform = 'scale(1)';
          }}
        >
          {disabled
            ? <Loader2 className="w-3.5 h-3.5 animate-spin" style={{ color: '#fb7185' }} />
            : <ArrowUp className="w-3.5 h-3.5 text-white" />
          }
        </button>
      </div>

      <p className="text-center text-[10px] mt-2" style={{ color: 'rgba(255,255,255,0.15)' }}>
        Enter to send · Shift+Enter for new line
      </p>
    </div>
  );
}
