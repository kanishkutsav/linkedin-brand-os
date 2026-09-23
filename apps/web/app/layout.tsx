import React from 'react';
import './globals.css';

export const metadata = {
  title: 'Brand OS — Personal Brand Manager',
  description: 'AI-powered personal brand management with human approval at the center.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
