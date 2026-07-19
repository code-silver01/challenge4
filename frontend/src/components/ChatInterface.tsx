import { useState, useRef, useEffect } from 'react';
import { Send, Loader2, Bot } from 'lucide-react';
import { type ChatMessage } from '../api';

interface Props {
  sessionId: string | null;
  messages: ChatMessage[];
  isLoading: boolean;
  onSendMessage: (msg: string) => void;
  placeholder?: string;
}

export function ChatInterface({ sessionId, messages, isLoading, onSendMessage, placeholder = "Ask me anything..." }: Props) {
  const [input, setInput] = useState('');
  const endOfMessagesRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endOfMessagesRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (input.trim() && !isLoading) {
      onSendMessage(input);
      setInput('');
    }
  };

  return (
    <div className="flex flex-col h-full bg-gray-900/50 backdrop-blur-md rounded-xl shadow-lg border border-gray-800 overflow-hidden">
      {/* Header */}
      <div className="bg-gray-900 border-b border-gray-800 text-white p-4 font-medium flex items-center gap-2">
        <Bot size={20} className="text-fifa-red" />
        <span>OffsideOperations</span>
      </div>

      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-transparent">
        {!messages || messages.length === 0 ? (
          <div className="text-center text-gray-500 mt-10">
            <Bot size={48} className="mx-auto mb-4 opacity-50" />
            <p>How can I help you today?</p>
          </div>
        ) : (
          messages.map((msg, idx) => (
            <div
              key={idx}
              className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[80%] rounded-2xl px-4 py-2 ${
                  msg.role === 'user'
                    ? 'bg-fifa-red text-white rounded-br-none'
                    : 'bg-gray-800 text-gray-200 border border-gray-700 shadow-sm rounded-bl-none'
                }`}
              >
                <p className="whitespace-pre-wrap">{msg.content}</p>
                {msg.data && (
                  <div className="mt-2 text-xs bg-gray-900 p-2 rounded text-gray-400 overflow-x-auto">
                    <pre>{JSON.stringify(msg.data, null, 2)}</pre>
                  </div>
                )}
              </div>
            </div>
          ))
        )}
        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-gray-800 border border-gray-700 shadow-sm rounded-2xl rounded-bl-none px-4 py-3">
              <Loader2 className="animate-spin text-fifa-red" size={20} />
            </div>
          </div>
        )}
        <div ref={endOfMessagesRef} />
      </div>

      {/* Input Area */}
      <div className="p-3 bg-gray-900 border-t border-gray-800">
        <form onSubmit={handleSubmit} className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            disabled={isLoading || !sessionId}
            placeholder={sessionId ? placeholder : "Connecting..."}
            className="flex-1 px-4 py-2 bg-gray-800 text-white border border-gray-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-fifa-red focus:border-transparent placeholder-gray-500"
          />
          <button
            type="submit"
            disabled={!input.trim() || isLoading || !sessionId}
            className="p-2 bg-fifa-red text-white rounded-lg hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <Send size={20} />
          </button>
        </form>
      </div>
    </div>
  );
}
