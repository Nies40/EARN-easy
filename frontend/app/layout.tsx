import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Easyearn — Earn, Refer & Withdraw with M-Pesa',
  description: 'The multi-level earning + wallet platform. Watch videos, like photos, answer trivia, and refer friends to earn Ksh. Withdraw instantly via M-Pesa.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet" />
      </head>
      <body>{children}</body>
    </html>
  );
}