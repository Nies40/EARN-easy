import Link from 'next/link';
import { Navbar } from './components/Navbar';
import { Footer } from './components/Footer';

export default function LandingPage() {
  return (
    <div className="min-h-screen overflow-x-hidden">
      <Navbar />

      {/* Hero */}
      <section className="relative pt-32 pb-20 px-4 sm:px-6">
        <div className="absolute inset-0 overflow-hidden -z-10">
          <div className="absolute top-20 left-1/4 w-72 h-72 bg-pink/20 rounded-full blur-3xl" />
          <div className="absolute top-40 right-1/4 w-96 h-96 bg-blue/20 rounded-full blur-3xl" />
        </div>
        <div className="max-w-4xl mx-auto text-center fade-in">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-pink/10 border border-pink/20 mb-6">
            <span className="text-xs font-medium text-pink-light">✨ Now with Credits System</span>
          </div>
          <h1 className="text-4xl sm:text-6xl font-extrabold leading-tight">
            Earn <span className="gradient-text">Ksh</span> by doing
            <br />
            what you love
          </h1>
          <p className="text-lg text-gray-400 mt-6 max-w-2xl mx-auto">
            Watch videos, like photos, answer trivia, and refer friends.
            Build your wallet balance and withdraw instantly via M-Pesa.
          </p>
          <div className="mt-10 flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link href="/auth?mode=signup" className="btn-primary text-base px-8 py-4">
              Get Started — It's Free
            </Link>
            <Link href="/auth?mode=login" className="btn-secondary text-base px-8 py-4">
              Sign In
            </Link>
          </div>
          <div className="mt-8 flex items-center justify-center gap-6 text-sm text-gray-500">
            <span className="flex items-center gap-2">
              <span className="text-green-400">✓</span> No upfront fees
            </span>
            <span className="flex items-center gap-2">
              <span className="text-green-400">✓</span> Instant M-Pesa withdrawals
            </span>
          </div>
        </div>
      </section>

      {/* Stats bar */}
      <section className="px-4 sm:px-6 py-8">
        <div className="max-w-5xl mx-auto grid grid-cols-3 gap-4 card p-6 sm:p-8">
          <div className="text-center">
            <p className="text-2xl sm:text-3xl font-bold gradient-text">4 Ways</p>
            <p className="text-xs text-gray-500 mt-1">to earn credits</p>
          </div>
          <div className="text-center border-x border-dark-600">
            <p className="text-2xl sm:text-3xl font-bold text-blue-light">Ksh 50</p>
            <p className="text-xs text-gray-500 mt-1">per referral bonus</p>
          </div>
          <div className="text-center">
            <p className="text-2xl sm:text-3xl font-bold text-pink">24/7</p>
            <p className="text-xs text-gray-500 mt-1">always earning</p>
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="px-4 sm:px-6 py-20">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-12">
            <h2 className="text-3xl sm:text-4xl font-bold">Everything you need to <span className="gradient-text">earn</span></h2>
            <p className="text-gray-500 mt-4">A complete wallet and earning platform in one place</p>
          </div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {/* Wallet */}
            <div className="card p-6 card-hover">
              <div className="w-12 h-12 rounded-xl bg-pink/10 flex items-center justify-center mb-4">
                <svg className="w-6 h-6 text-pink" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" /></svg>
              </div>
              <h3 className="font-semibold text-lg">Wallet Engine</h3>
              <p className="text-sm text-gray-500 mt-2">
                Track your balance, total earned, and total withdrawn. Deposit and withdraw via M-Pesa with full transaction history.
              </p>
            </div>

            {/* Credits */}
            <div className="card p-6 card-hover">
              <div className="w-12 h-12 rounded-xl bg-blue/10 flex items-center justify-center mb-4">
                <svg className="w-6 h-6 text-blue-light" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.915a1 1 0 00.95-.69l1.519-4.674z" /></svg>
              </div>
              <h3 className="font-semibold text-lg">Credits System</h3>
              <p className="text-sm text-gray-500 mt-2">
                Earn credits by completing tasks. Convert them to Ksh anytime — 10 credits = 1 Ksh. It's that simple.
              </p>
            </div>

            {/* Referrals */}
            <div className="card p-6 card-hover">
              <div className="w-12 h-12 rounded-xl bg-green-500/10 flex items-center justify-center mb-4">
                <svg className="w-6 h-6 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" /></svg>
              </div>
              <h3 className="font-semibold text-lg">Affiliate Referrals</h3>
              <p className="text-sm text-gray-500 mt-2">
                Share your unique earning link via WhatsApp or Telegram. Earn Ksh 50 for every friend who activates.
              </p>
            </div>

            {/* Tasks */}
            <div className="card p-6 card-hover">
              <div className="w-12 h-12 rounded-xl bg-purple-500/10 flex items-center justify-center mb-4">
                <svg className="w-6 h-6 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 10l4.553-2.276-1 4.5 4.5 1L21 21l-5-5M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
              </div>
              <h3 className="font-semibold text-lg">Task Module</h3>
              <p className="text-sm text-gray-500 mt-2">
                Watch videos, like photos, and answer trivia to earn credits. New tasks added regularly.
              </p>
            </div>

            {/* M-Pesa */}
            <div className="card p-6 card-hover">
              <div className="w-12 h-12 rounded-xl bg-green-600/10 flex items-center justify-center mb-4">
                <svg className="w-6 h-6 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2m0-4c1.657 0 3 .895 3 2s-1.343 2-3 2m-9 2h18M5 21h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v14a2 2 0 002 2z" /></svg>
              </div>
              <h3 className="font-semibold text-lg">M-Pesa Integration</h3>
              <p className="text-sm text-gray-500 mt-2">
                Deposit and withdraw using Safaricom's Daraja API. Fast, secure, and built for Kenya.
              </p>
            </div>

            {/* Dashboard */}
            <div className="card p-6 card-hover">
              <div className="w-12 h-12 rounded-xl bg-orange-500/10 flex items-center justify-center mb-4">
                <svg className="w-6 h-6 text-orange-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" /></svg>
              </div>
              <h3 className="font-semibold text-lg">Live Dashboard</h3>
              <p className="text-sm text-gray-500 mt-2">
                Real-time earnings and referral trends with interactive charts. See exactly how you're growing.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="px-4 sm:px-6 py-20 bg-dark-800/50">
        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-12">
            <h2 className="text-3xl sm:text-4xl font-bold">How <span className="gradient-text">it works</span></h2>
            <p className="text-gray-500 mt-4">Start earning in 3 simple steps</p>
          </div>
          <div className="grid sm:grid-cols-3 gap-8">
            <div className="text-center">
              <div className="w-16 h-16 rounded-2xl bg-pink/10 border border-pink/20 flex items-center justify-center mx-auto mb-4">
                <span className="text-2xl font-bold text-pink">1</span>
              </div>
              <h3 className="font-semibold">Create your account</h3>
              <p className="text-sm text-gray-500 mt-2">
                Sign up free with your email. Get your unique referral code instantly.
              </p>
            </div>
            <div className="text-center">
              <div className="w-16 h-16 rounded-2xl bg-blue/10 border border-blue/20 flex items-center justify-center mx-auto mb-4">
                <span className="text-2xl font-bold text-blue-light">2</span>
              </div>
              <h3 className="font-semibold">Complete tasks & refer</h3>
              <p className="text-sm text-gray-500 mt-2">
                Watch videos, like photos, answer trivia, and share your link with friends.
              </p>
            </div>
            <div className="text-center">
              <div className="w-16 h-16 rounded-2xl bg-green-500/10 border border-green-500/20 flex items-center justify-center mx-auto mb-4">
                <span className="text-2xl font-bold text-green-400">3</span>
              </div>
              <h3 className="font-semibold">Withdraw via M-Pesa</h3>
              <p className="text-sm text-gray-500 mt-2">
                Convert credits to Ksh and withdraw directly to your M-Pesa wallet.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Ways to earn */}
      <section id="earn" className="px-4 sm:px-6 py-20">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-12">
            <h2 className="text-3xl sm:text-4xl font-bold">Ways to <span className="gradient-text">earn</span></h2>
            <p className="text-gray-500 mt-4">Four ways to build your balance</p>
          </div>
          <div className="grid sm:grid-cols-2 gap-6">
            <div className="card p-6 flex items-start gap-4">
              <div className="w-10 h-10 rounded-lg bg-pink/10 flex items-center justify-center flex-shrink-0">
                <svg className="w-5 h-5 text-pink" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
              </div>
              <div>
                <h3 className="font-semibold">Watch Videos</h3>
                <p className="text-sm text-gray-500 mt-1">Earn up to 20 credits per video you watch</p>
              </div>
            </div>
            <div className="card p-6 flex items-start gap-4">
              <div className="w-10 h-10 rounded-lg bg-blue/10 flex items-center justify-center flex-shrink-0">
                <svg className="w-5 h-5 text-blue-light" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" /></svg>
              </div>
              <div>
                <h3 className="font-semibold">Like Photos</h3>
                <p className="text-sm text-gray-500 mt-1">Earn 10 credits for each photo you like</p>
              </div>
            </div>
            <div className="card p-6 flex items-start gap-4">
              <div className="w-10 h-10 rounded-lg bg-purple-500/10 flex items-center justify-center flex-shrink-0">
                <svg className="w-5 h-5 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.018 2.907-.542.104-.992.583-.992 1.182m0 0V15m0 0h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
              </div>
              <div>
                <h3 className="font-semibold">Answer Trivia</h3>
                <p className="text-sm text-gray-500 mt-1">Earn 15 credits for each correct trivia answer</p>
              </div>
            </div>
            <div className="card p-6 flex items-start gap-4">
              <div className="w-10 h-10 rounded-lg bg-green-500/10 flex items-center justify-center flex-shrink-0">
                <svg className="w-5 h-5 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" /></svg>
              </div>
              <div>
                <h3 className="font-semibold">Refer Friends</h3>
                <p className="text-sm text-gray-500 mt-1">Earn Ksh 50 for every friend who signs up & activates</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="px-4 sm:px-6 py-20">
        <div className="max-w-3xl mx-auto text-center">
          <div className="card p-10 sm:p-14 gradient-bg border-pink/30">
            <h2 className="text-3xl sm:text-4xl font-bold">Ready to start <span className="gradient-text">earning?</span></h2>
            <p className="text-gray-400 mt-4">
              Join Easyearn today. It's free, and you can withdraw your first Ksh in minutes.
            </p>
            <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-4">
              <Link href="/auth?mode=signup" className="btn-primary text-base px-8 py-4">
                Create Free Account
              </Link>
              <Link href="/auth?mode=login" className="btn-secondary text-base px-8 py-4">
                I already have an account
              </Link>
            </div>
          </div>
        </div>
      </section>

      <Footer />
    </div>
  );
}