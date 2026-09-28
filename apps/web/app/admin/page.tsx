'use client';

import { useEffect } from 'react';

export default function AdminRoute() {
  useEffect(() => {
    window.location.replace('/?admin=1');
  }, []);

  return (
    <main style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', fontFamily: 'sans-serif' }}>
      <div style={{ textAlign: 'center' }}>
        <strong>Opening admin workspace…</strong>
        <p style={{ color: '#6b7d92', fontSize: 13 }}>Your account permissions will be checked by Suvacya.</p>
      </div>
    </main>
  );
}
