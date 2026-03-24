import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Loader2, FileText, Check, X } from 'lucide-react';

function PasswordStrengthBar({ password }: { password: string }) {
  const checks = [
    password.length >= 8,
    /[A-Z]/.test(password),
    /[0-9]/.test(password),
    /[^a-zA-Z0-9]/.test(password),
  ];
  const strength = checks.filter(Boolean).length;
  const colors = ['', 'bg-red-500', 'bg-orange-400', 'bg-yellow-400', 'bg-emerald-500'];
  const labels = ['', 'Weak', 'Fair', 'Good', 'Strong'];

  if (!password) return null;

  return (
    <div className="space-y-1.5 animate-fade-in">
      <div className="flex gap-1">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className={`h-1 flex-1 rounded-full transition-all duration-300 ${i <= strength ? colors[strength] : 'bg-white/10'}`} />
        ))}
      </div>
      <p className="text-xs" style={{ color: strength >= 3 ? '#4ade80' : strength === 2 ? '#facc15' : '#f87171' }}>
        {labels[strength]}
      </p>
    </div>
  );
}

export default function Register() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { register } = useAuth();
  const navigate = useNavigate();

  const passwordsMatch = confirmPassword ? password === confirmPassword : null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }
    setError('');
    setLoading(true);
    try {
      await register(email, password);
      navigate('/', { replace: true });
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to register');
    } finally {
      setLoading(false);
    }
  };

  const inputStyle = {
    background: 'rgba(255,255,255,0.05)',
    border: '1px solid rgba(255,255,255,0.1)',
    outline: 'none'
  };
  const onFocus = (e: React.FocusEvent<HTMLInputElement>) => {
    e.target.style.borderColor = 'rgba(244,63,94,0.6)';
    e.target.style.boxShadow = '0 0 0 3px rgba(244,63,94,0.15)';
  };
  const onBlur = (e: React.FocusEvent<HTMLInputElement>) => {
    e.target.style.borderColor = 'rgba(255,255,255,0.1)';
    e.target.style.boxShadow = 'none';
  };

  return (
    <div className="min-h-screen flex bg-background">
      {/* Left panel */}
      <div className="hidden lg:flex lg:w-1/2 relative flex-col items-center justify-center p-12 overflow-hidden">
        <div className="absolute inset-0" style={{
          background: 'radial-gradient(ellipse at 60% 40%, rgba(244,63,94,0.18) 0%, transparent 70%), radial-gradient(ellipse at 20% 70%, rgba(251,113,133,0.1) 0%, transparent 60%), #0a0812'
        }} />
        <div className="absolute top-1/3 right-1/4 w-72 h-72 rounded-full orb-animate" style={{
          background: 'radial-gradient(circle, rgba(244,63,94,0.18) 0%, transparent 70%)',
          filter: 'blur(50px)'
        }} />
        <div className="relative z-10 text-center max-w-md">
          <div className="flex items-center justify-center gap-3 mb-8">
            <div className="p-3 rounded-2xl btn-rose">
              <FileText className="w-7 h-7 text-white" />
            </div>
            <span className="text-2xl font-bold tracking-tight text-white">Pinpoint PDF</span>
          </div>
          <h2 className="text-4xl font-bold text-white mb-4 leading-tight">
            Your documents,<br />
            <span className="gradient-text">supercharged.</span>
          </h2>
          <p className="text-lg" style={{ color: 'rgba(255,255,255,0.5)' }}>
            Join thousands of users getting instant answers from their PDFs.
          </p>
        </div>
      </div>

      {/* Right panel — form */}
      <div className="w-full lg:w-1/2 flex items-center justify-center p-8" style={{ background: '#0d0a14' }}>
        <div className="w-full max-w-md animate-fade-in">
          <div className="lg:hidden flex items-center gap-2 mb-8">
            <div className="p-2 rounded-xl btn-rose">
              <FileText className="w-5 h-5 text-white" />
            </div>
            <span className="text-xl font-bold text-white">Pinpoint PDF</span>
          </div>

          <div className="glass-card rounded-2xl p-8">
            <div className="mb-8">
              <h1 className="text-2xl font-bold text-white mb-1">Create account</h1>
              <p style={{ color: 'rgba(255,255,255,0.4)' }} className="text-sm">Get started for free today</p>
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
                  className="w-full px-4 py-3 rounded-xl text-sm text-white placeholder-white/30 transition-all duration-200"
                  style={inputStyle}
                  onFocus={onFocus}
                  onBlur={onBlur}
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-sm font-medium" style={{ color: 'rgba(255,255,255,0.7)' }}>Password</label>
                <input
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Min. 8 characters"
                  className="w-full px-4 py-3 rounded-xl text-sm text-white placeholder-white/30 transition-all duration-200"
                  style={inputStyle}
                  onFocus={onFocus}
                  onBlur={onBlur}
                />
                <PasswordStrengthBar password={password} />
              </div>

              <div className="space-y-1.5">
                <label className="text-sm font-medium" style={{ color: 'rgba(255,255,255,0.7)' }}>Confirm password</label>
                <div className="relative">
                  <input
                    type="password"
                    required
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="••••••••"
                    className="w-full px-4 py-3 pr-10 rounded-xl text-sm text-white placeholder-white/30 transition-all duration-200"
                    style={{
                      ...inputStyle,
                      borderColor: confirmPassword
                        ? passwordsMatch ? 'rgba(74,222,128,0.5)' : 'rgba(239,68,68,0.5)'
                        : 'rgba(255,255,255,0.1)'
                    }}
                    onFocus={onFocus}
                    onBlur={onBlur}
                  />
                  {confirmPassword && (
                    <span className="absolute right-3 top-1/2 -translate-y-1/2">
                      {passwordsMatch
                        ? <Check className="w-4 h-4 text-emerald-400" />
                        : <X className="w-4 h-4 text-red-400" />
                      }
                    </span>
                  )}
                </div>
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
                className="w-full py-3 rounded-xl font-semibold text-sm btn-rose disabled:opacity-50 disabled:cursor-not-allowed disabled:transform-none"
              >
                {loading ? (
                  <span className="flex items-center justify-center gap-2">
                    <Loader2 className="h-4 w-4 animate-spin" /> Creating account…
                  </span>
                ) : 'Create account'}
              </button>
            </form>

            <p className="mt-6 text-center text-sm" style={{ color: 'rgba(255,255,255,0.35)' }}>
              Already have an account?{' '}
              <Link to="/login" className="font-medium transition-colors" style={{ color: '#fb7185', opacity: 0.85 }}>
                Sign in
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
