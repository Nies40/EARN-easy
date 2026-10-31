'use client';

import { useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { apiClient } from '../lib/api';

export default function AuthPage() {
  const searchParams = useSearchParams();
  const initialMode = (searchParams.get('mode') === 'signup' ? 'signup' : 'login') as 'login' | 'signup';
  const [mode, setMode] = useState<'login' | 'signup'>(initialMode);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [username, setUsername] = useState('');
  const [phone, setPhone] = useState('');
  const router = useRouter();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      if (mode === 'signup') {
        await apiClient.signup({ name, email, password, username: username || undefined, phone: phone || undefined });
      } else {
        await apiClient.login({ identifier: identifier || email, password });
      }
      router.push('/dashboard');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-md fade-in">
        <div className="text-center mb-8">
          <Link href="/" className="inline-block">
            <h1 className="text-4xl font-bold gradient-text">Easyearn</h1>
          </Link>
          <p className="text-gray-500 mt-2">
            {mode === 'login' ? 'Welcome back' : 'Create your account'}
          </p>
        </div>

        <div className="card p-8">
          <div className="flex gap-2 mb-6 p-1 bg-dark-900 rounded-xl">
            <button
              onClick={() => setMode('login')}
              className={`flex-1 py-2 rounded-lg text-sm font-medium transition ${mode === 'login' ? 'bg-pink text-white' : 'text-gray-500'}`}
            >
              Sign In
            </button>
            <button
              onClick={() => setMode('signup')}
              className={`flex-1 py-2 rounded-lg text-sm font-medium transition ${mode === 'signup' ? 'bg-pink text-white' : 'text-gray-500'}`}
            >
              Register
            </button>
          </div>

          {error && (
            <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            {mode === 'signup' && (
              <>
                <div>
                  <input type="text" placeholder="Full name" value={name} onChange={(e) => setName(e.target.value)} required />
                </div>
                <div>
                  <input type="text" placeholder="Username (optional)" value={username} onChange={(e) => setUsername(e.target.value)} />
                </div>
              </>
            )}
            <div>
              <input type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </div>
            {mode === 'login' && (
              <div>
                <input type="text" placeholder="Email or username" value={identifier} onChange={(e) => setIdentifier(e.target.value)} />
                <p className="text-xs text-gray-600 mt-1">Leave blank to use email above</p>
              </div>
            )}
            {mode === 'signup' && (
              <div>
                <input type="tel" placeholder="Phone (optional)" value={phone} onChange={(e) => setPhone(e.target.value)} />
              </div>
            )}
            <div>
              <input type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} />
            </div>
            <button type="submit" disabled={loading} className="btn-primary w-full flex items-center justify-center gap-2">
              {loading && <span className="loader" />}
              {mode === 'login' ? 'Sign In' : 'Create Account'}
            </button>
          </form>

          {mode === 'login' && (
            <button
              onClick={() => router.push('/forgot-password')}
              className="mt-4 text-sm text-blue-light hover:text-pink transition w-full text-center"
            >
              Forgot password?
            </button>
          )}

          <div className="mt-6 pt-6 border-t border-dark-600">
            <button
              onClick={async () => {
                setLoading(true);
                try {
                  const cred = navigator.credentials?.get({ password: true } as PasswordCredentialInit) as Promise<PasswordCredential | null>;
                  if (cred) {
                    const c = await cred;
                    if (c) {
                      setIdentifier(c.id);
                      // @ts-ignore
                      setPassword(c.password || '');
                    }
                  }
                } catch {
                  // User dismissed
                } finally {
                  setLoading(false);
                }
              }}
              className="btn-secondary w-full flex items-center justify-center gap-2"
            >
              <svg className="w-5 h-5" viewBox="0 0 24 24"><path fill="currentColor" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/><path fill="currentColor" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="currentColor" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"/><path fill="currentColor" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/></svg>
              Use Google Saved Password
            </button>
          </div>

          <p className="mt-6 text-center text-sm text-gray-500">
            {mode === 'login' ? "Don't have an account? " : 'Already have an account? '}
            <button
              onClick={() => setMode(mode === 'login' ? 'signup' : 'login')}
              className="text-pink hover:text-pink-light transition font-medium"
            >
              {mode === 'login' ? 'Register' : 'Sign In'}
            </button>
          </p>
        </div>

        <p className="mt-6 text-center text-sm text-gray-600">
          <Link href="/" className="hover:text-pink transition">← Back to home</Link>
        </p>
      </div>
    </div>
  );
}