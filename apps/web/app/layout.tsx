import React from 'react';
import type { Metadata, Viewport } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Suvacya — Personal Brand Manager',
  description: 'AI-powered personal brand management with human approval at the center.',
  manifest: '/manifest.webmanifest',
  applicationName: 'Suvacya',
  appleWebApp: {
    capable: true,
    title: 'Suvacya',
    statusBarStyle: 'black-translucent',
  },
  icons: {
    icon: '/icons/icon-192.svg',
    shortcut: '/icons/icon-192.svg',
    apple: '/icons/icon-192.svg',
  },
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
  themeColor: '#062b55',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
