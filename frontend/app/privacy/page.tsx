import Link from 'next/link';
import { Navbar } from '../components/Navbar';
import { Footer } from '../components/Footer';

export default function PrivacyPage() {
  return (
    <div className="min-h-screen">
      <Navbar />
      <div className="max-w-3xl mx-auto px-4 sm:px-6 pt-32 pb-20">
        <h1 className="text-3xl font-bold gradient-text">Privacy Policy</h1>
        <p className="text-gray-500 mt-2">Last updated: October 2026</p>
        <div className="mt-8 space-y-6 text-gray-400 text-sm leading-relaxed">
          <section>
            <h2 className="text-lg font-semibold text-white">1. Information We Collect</h2>
            <p className="mt-2">We collect your name, email, phone number, and username when you register. We also track your wallet balance, transactions, credits, and referral activity.</p>
          </section>
          <section>
            <h2 className="text-lg font-semibold text-white">2. How We Use Your Data</h2>
            <p className="mt-2">Your data is used to operate the platform, process M-Pesa transactions, send verification and notification emails, and prevent abuse.</p>
          </section>
          <section>
            <h2 className="text-lg font-semibold text-white">3. Data Security</h2>
            <p className="mt-2">Passwords are stored as bcrypt hashes. Authentication tokens are stored as SHA-256 hashes. Email payloads are encrypted at rest. We never share your data with third parties except as required by law.</p>
          </section>
          <section>
            <h2 className="text-lg font-semibold text-white">4. M-Pesa & Payments</h2>
            <p className="mt-2">Payment processing is handled via Safaricom's Daraja API and Paystack. We do not store your M-Pesa PIN. Transaction references are logged for audit purposes.</p>
          </section>
          <section>
            <h2 className="text-lg font-semibold text-white">5. Your Rights</h2>
            <p className="mt-2">You may request deletion of your account at any time. Contact us to exercise your data rights.</p>
          </section>
        </div>
        <Link href="/" className="mt-10 inline-block text-sm text-pink hover:text-pink-light transition">← Back to home</Link>
      </div>
      <Footer />
    </div>
  );
}