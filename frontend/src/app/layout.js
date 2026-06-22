import './globals.css';

export const metadata = {
  title: 'Plum Claims — Health Insurance Claims Processing',
  description: 'AI-powered multi-agent health insurance claims processing system by Plum',
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <nav className="navbar">
          <div className="navbar-inner">
            <a href="/" className="navbar-brand">
              <div className="logo">P</div>
              <div>
                <div className="brand-text">Plum Claims</div>
                <div className="brand-sub">AI Processing Engine</div>
              </div>
            </a>
            <div className="navbar-links">
              <a href="/" className="nav-link">Dashboard</a>
              <a href="/submit" className="nav-link">Submit Claim</a>
              <a href="/claims" className="nav-link">Claims</a>
              <a href="/eval" className="nav-link">Eval Report</a>
            </div>
          </div>
        </nav>
        <main className="app-container">
          <div className="page-content">
            {children}
          </div>
        </main>
      </body>
    </html>
  );
}
