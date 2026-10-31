import Link from 'next/link';
import { Navbar } from '../components/Navbar';
import { Footer } from '../components/Footer';

export default function TermsPage() {
  return (
    <div className="min-h-screen">
      <Navbar />
      <div className="max-w-3xl mx-auto px-4 sm:px-6 pt-32 pb-20">
        <h1 className="text-3xl font-bold gradient-text">Terms of Service</h1>
        <p className="text-gray-500 mt-2">Last updated: October 2026</p>
        <div className="mt-8 space-y-6 text-gray-400 text-sm leading-relaxed">
          <section>
            <h2 className="text-lg font-semibold text-white">1. Acceptance of Terms</h2>
            <p className="mt-2">By creating an account on Easyearn, you agree to these Terms of Service. If you do not agree, do not use the platform.</p>
          </section>
          <section>
            <h2 className="text-lg font-semibold text-white">2. Eligibility</h2>
            <p className="mt-2">You must be at least 18 years old and a resident of Kenya to use Easyearn. You must provide accurate information when registering.</p>
          </section>
          <section>
            <h2 className="text-lg font-semibold text-white">3. Earning & Withdrawals</h2>
            <p className="mt-2">Credits earned through tasks are converted to Ksh at the rate of 10 credits = 1 Ksh. Withdrawals are processed via M-Pesa and subject to admin approval. Minimum withdrawal amount may apply.</p>
          </section>
          <section>
            <h2 className="text-lg font-semibold text-white">4. Referral Program</h2>
            <p className="mt-2">Referral bonuses (Ksh 50) are credited when a referred user activates their account. Abuse of the referral system, including self-referrals or fake accounts, will result in forfeiture of bonuses and account suspension.</p>
          </section>
          <section>
            <h2 className="text-lg font-semibold text-white">5. Prohibited Conduct</h2>
            <p className="mt-2">You may not use bots, automation, or any unfair means to complete tasks or inflate earnings. Violations result in immediate account termination.</p>
          </section>
          <section>
            <h2 className="text-lg font-semibold text-white">6. Contact</h2>
            <p className="mt-2">For questions about these terms, contact Nies Technologies.</p>
          </section>
        </div>
        <Link href="/" className="mt-10 inline-block text-sm text-pink hover:text-pink-light transition">← Back to home</Link>
      </div>
      <Footer />
    </div>
  );
}