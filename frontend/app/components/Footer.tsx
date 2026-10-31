import Link from 'next/link';

export function Footer() {
  return (
    <footer className="border-t border-dark-600 mt-20">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-12">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-8">
          <div className="col-span-2">
            <h3 className="text-lg font-bold gradient-text">Easyearn</h3>
            <p className="text-sm text-gray-500 mt-2 max-w-xs">
              The multi-level earning + wallet platform. Earn Ksh by completing tasks and referring friends.
            </p>
          </div>
          <div>
            <h4 className="text-sm font-semibold text-gray-400 mb-3">Product</h4>
            <ul className="space-y-2 text-sm">
              <li><Link href="/#features" className="text-gray-500 hover:text-pink transition">Features</Link></li>
              <li><Link href="/#how-it-works" className="text-gray-500 hover:text-pink transition">How it works</Link></li>
              <li><Link href="/#earn" className="text-gray-500 hover:text-pink transition">Ways to earn</Link></li>
              <li><Link href="/auth?mode=signup" className="text-gray-500 hover:text-pink transition">Register</Link></li>
            </ul>
          </div>
          <div>
            <h4 className="text-sm font-semibold text-gray-400 mb-3">Legal</h4>
            <ul className="space-y-2 text-sm">
              <li><Link href="/terms" className="text-gray-500 hover:text-pink transition">Terms of Service</Link></li>
              <li><Link href="/privacy" className="text-gray-500 hover:text-pink transition">Privacy Policy</Link></li>
            </ul>
          </div>
        </div>
        <div className="mt-10 pt-6 border-t border-dark-600 flex flex-col sm:flex-row items-center justify-between gap-4">
          <p className="text-xs text-gray-600">© 2026 Easyearn by Nies Technologies. All rights reserved.</p>
          <p className="text-xs text-gray-600">Powered by M-Pesa Daraja & Paystack</p>
        </div>
      </div>
    </footer>
  );
}