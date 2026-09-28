export default function PrivacyPage() {
  return (
    <main style={{ maxWidth: 860, margin: '0 auto', padding: '48px 24px', fontFamily: 'system-ui, sans-serif', color: '#344054', lineHeight: 1.7 }}>
      <h1>Suvacya Privacy Policy</h1>
      <p><b>QA draft — legal review required before production publication.</b></p>
      <p>Suvacya processes account, LinkedIn connection, Brand DNA, content, research, learning and product-usage information to provide the personal brand management service.</p>
      <h2>How information is used</h2>
      <ul>
        <li>Account and authentication information is used to authorize access.</li>
        <li>LinkedIn profile and publishing information is used only for the connected product workflows and permissions granted to the app.</li>
        <li>Brand DNA, approved content and explicit personal insights are used to personalize research and content generation.</li>
        <li>AI providers may receive the minimum context required for an enabled generation task, subject to provider configuration and contractual terms.</li>
      </ul>
      <h2>Your controls</h2>
      <p>You can review and correct Brand DNA, delete personal insights, export application data, disconnect LinkedIn, and request account deletion from the product. Deletion is subject to any retention required by applicable law or legitimate security/compliance obligations.</p>
      <h2>Security</h2>
      <p>Suvacya uses server-side authorization, protected browser sessions, CSRF controls, encrypted LinkedIn access tokens, rate limiting and database access controls.</p>
      <h2>Contact and grievance redressal</h2>
      <p>The production policy must name the responsible entity, privacy contact, grievance contact, applicable retention periods, processor list and jurisdiction-specific legal basis after legal review.</p>
      <p><a href="/terms">Terms of Service</a> · <a href="/">Back to Suvacya</a></p>
    </main>
  );
}
