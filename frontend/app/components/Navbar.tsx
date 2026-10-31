'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { apiClient, type PublicUser } from '../lib/api';

export function Navbar() {
  const [user, setUser] = useState<PublicUser | null>(null);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    apiClient.me().then((r) => setUser(r.user)).catch(() => {});
    const onScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener('scroll', onScroll);
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  return (
    <header className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${scrolled ? 'bg-dark-900/90 backdrop-blur-md border-b border-dark-600' : 'bg-transparent'}`}>
      <nav className="max-w-6xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2">
          <span className="text-xl font-extrabold gradient-text">Easyearn</span>
        </Link>
        <div className="flex items-center gap-3 sm:gap-4">
          <Link href="/#features" className="hidden sm:block text-sm text-gray-400 hover:text-white transition">
            Features
          </Link>
          <Link href="/#how-it-works" className="hidden sm:block text-sm text-gray-400 hover:text-white transition">
            How it works
          </Link>
          <Link href="/#earn" className="hidden sm:block text-sm text-gray-400 hover:text-white transition">
            Earn
          </Link>
          {user ? (
            <Link href="/dashboard" className="btn-primary text-sm">
              Dashboard →
            </Link>
          ) : (
            <>
              <Link href="/auth?mode=login" className="text-sm text-gray-300 hover:text-white transition px-3 py-2">
                Sign In
              </Link>
              <Link href="/auth?mode=signup" className="btn-primary text-sm">
                Register
              </Link>
            </>
          )}
        </div>
      </nav>
    </header>
  );
}