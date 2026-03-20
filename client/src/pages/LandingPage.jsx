import { Link } from 'react-router-dom';

function LandingPage() {
  return (
    <div className="landing">
      <h1>Welcome to LLM Data Analyst Agent</h1>
      <p>Your intelligent assistant for database analysis.</p>
      <div className="cta-buttons">
        <Link to="/register" className="cta-button">Get Started</Link>
        <Link to="/login" className="cta-button secondary">Login</Link>
      </div>
    </div>
  );
}

export default LandingPage;