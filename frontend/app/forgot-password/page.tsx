'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { apiClient } from '../lib/api';

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);
  const router = useRouter();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await apiClient.login({ identifier: email, password: '' }).catch(() => {});
      // Use the forgot password endpoint
      await fetch('/api/password/forgot', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ email }),
      });
      setSent(true);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-md fade-in">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold gradient-text">Reset Password</h1>
        </div>
        <div className="card p-8">
          {sent ? (
            <p className="text-center text-gray-400">
              If an account matches that email, a reset link has been sent.
            </p>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <input type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} required />
              <button type="submit" disabled={loading} className="btn-primary w-full flex items-center justify-center gap-2">
                {loading && <span className="loader" />}
                Send Reset Link
              </button>
            </form>
          )}
          <button onClick={() => router.push('/')} className="mt-4 text-sm text-blue-light hover:text-pink transition w-full text-center">
            Back to login
          </button>
        </div>
      </div>
    </div>
  );
}