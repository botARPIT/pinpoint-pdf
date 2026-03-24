import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Loader2, FileText, Sparkles } from 'lucide-react';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login(email, password);
      navigate('/', { replace: true });
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Invalid email or password');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex bg-background">
      {/* Left panel — brand */}
      <div className="hidden lg:flex lg:w-1/2 relative flex-col items-center justify-center p-12 overflow-hidden">
        {/* Background gradient */}
        <div className="absolute inset-0" style={{
          background: 'radial-gradient(ellipse at 30% 50%, rgba(244,63,94,0.18) 0%, transparent 70%), radial-gradient(ellipse at 80% 20%, rgba(251,113,133,0.12) 0%, transparent 60%), #0a0812'
        }} />
        {/* Animated orbs */}
        <div className="absolute top-1/4 left-1/4 w-64 h-64 rounded-full orb-animate" style={{
          background: 'radial-gradient(circle, rgba(244,63,94,0.2) 0%, transparent 70%)',
          filter: 'blur(40px)'
        }} />
        <div className="absolute bottom-1/3 right-1/4 w-48 h-48 rounded-full orb-animate" style={{
          background: 'radial-gradient(circle, rgba(251,113,133,0.15) 0%, transparent 70%)',
          filter: 'blur(30px)',
          animationDelay: '2s'
        }} />

        <div className="relative z-10 text-center max-w-md">
          <div className="flex items-center justify-center gap-3 mb-8">
            <div className="p-3 rounded-2xl btn-rose">
              <FileText className="w-7 h-7 text-white" />
            </div>
            <span className="text-2xl font-bold tracking-tight text-white">Pinpoint PDF</span>
          </div>
          <h2 className="text-4xl font-bold text-white mb-4 leading-tight">
            Chat with your<br />
            <span className="gradient-text">documents.</span>
          </h2>
          <p className="text-lg" style={{ color: 'rgba(255,255,255,0.5)' }}>
            Upload any PDF and ask questions. Get instant, accurate answers with source citations.
          </p>
          <div className="mt-10 grid grid-cols-3 gap-4">
            {['Instant answers', 'Source citations', 'AI-powered RAG'].map((feat) => (
              <div key={feat} className="glass-card rounded-xl p-3">
                <Sparkles className="w-4 h-4 mb-1" style={{ color: '#fb7185' }} />
                <p className="text-xs font-medium text-white/70">{feat}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Right panel — form */}
      <div className="w-full lg:w-1/2 flex items-center justify-center p-8" style={{ background: '#0d0a14' }}>
        <div className="w-full max-w-md animate-fade-in">
          {/* Mobile logo */}
          <div className="lg:hidden flex items-center gap-2 mb-8">
            <div className="p-2 rounded-xl btn-rose">
              <FileText className="w-5 h-5 text-white" />
            </div>
            <span className="text-xl font-bold text-white">Pinpoint PDF</span>
          </div>

          <div className="glass-card rounded-2xl p-8">
            <div className="mb-8">
              <h1 className="text-2xl font-bold text-white mb-1">Welcome back</h1>
              <p style={{ color: 'rgba(255,255,255,0.4)' }} className="text-sm">Sign in to your account to continue</p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-5">
              <div className="space-y-1.5">
                <label className="text-sm font-medium" style={{ color: 'rgba(255,255,255,0.7)' }}>Email</label>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  className="w-full px-4 py-3 rounded-xl text-sm text-white placeholder-white/30 transition-all duration-200 input-rose"
                  style={{
                    background: 'rgba(255,255,255,0.05)',
                    border: '1px solid rgba(255,255,255,0.1)',
                    outline: 'none'
                  }}
                  onFocus={(e) => {
                    e.target.style.borderColor = 'rgba(244,63,94,0.6)';
                    e.target.style.boxShadow = '0 0 0 3px rgba(244,63,94,0.15)';
                  }}
                  onBlur={(e) => {
                    e.target.style.borderColor = 'rgba(255,255,255,0.1)';
                    e.target.style.boxShadow = 'none';
                  }}
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-sm font-medium" style={{ color: 'rgba(255,255,255,0.7)' }}>Password</label>
                <input
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full px-4 py-3 rounded-xl text-sm text-white placeholder-white/30 transition-all duration-200"
                  style={{
                    background: 'rgba(255,255,255,0.05)',
                    border: '1px solid rgba(255,255,255,0.1)',
                    outline: 'none'
                  }}
                  onFocus={(e) => {
                    e.target.style.borderColor = 'rgba(244,63,94,0.6)';
                    e.target.style.boxShadow = '0 0 0 3px rgba(244,63,94,0.15)';
                  }}
                  onBlur={(e) => {
                    e.target.style.borderColor = 'rgba(255,255,255,0.1)';
                    e.target.style.boxShadow = 'none';
                  }}
                />
              </div>

              {error && (
                <div className="rounded-xl px-4 py-3 text-sm animate-fade-in" style={{
                  background: 'rgba(239,68,68,0.1)',
                  border: '1px solid rgba(239,68,68,0.2)',
                  color: '#fca5a5'
                }}>
                  {error}
                </div>
              )}

              <button
                type="submit"
                disabled={loading}
                className="w-full py-3 rounded-xl font-semibold text-sm transition-all duration-200 btn-rose disabled:opacity-50 disabled:cursor-not-allowed disabled:transform-none"
              >
                {loading ? (
                  <span className="flex items-center justify-center gap-2">
                    <Loader2 className="h-4 w-4 animate-spin" /> Signing in…
                  </span>
                ) : 'Sign in'}
              </button>
            </form>

            <p className="mt-6 text-center text-sm" style={{ color: 'rgba(255,255,255,0.35)' }}>
              Don't have an account?{' '}
              <Link to="/register" className="font-medium transition-colors hover:opacity-100" style={{ color: '#fb7185', opacity: 0.85 }}>
                Create one
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
