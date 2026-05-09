// frontend/components/PageHeader.tsx
import React from "react";

type PageHeaderProps = {
  title: React.ReactNode;
  subtitle?: string;
  onLogout: () => void;
  /** Show "Dashboard" / "Back" primary button — pass the navigation handler */
  onDashboard?: () => void;
  /** Show "Profile" primary button instead (dashboard page only) */
  onProfile?: () => void;
  /** Extra classes appended to <header> (e.g. "shrink-0") */
  className?: string;
};

export default function PageHeader({
  title,
  subtitle,
  onLogout,
  onDashboard,
  onProfile,
  className = "",
}: PageHeaderProps) {
  return (
    <header className={`site-header${className ? ` ${className}` : ""}`}>
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <h1 className="page-title leading-tight">{title}</h1>
          {subtitle && (
            <p className="mt-1 page-subtitle hidden md:block">{subtitle}</p>
          )}
        </div>

        <div className="flex items-center gap-3 shrink-0">
          {onProfile && (
            <button onClick={onProfile} className="btn-primary">
              Profile
            </button>
          )}
          {onDashboard && (
            <button onClick={onDashboard} className="btn-primary">
              <span className="hidden md:inline">Dashboard</span>
              <span className="md:hidden">Back</span>
            </button>
          )}
          <button onClick={onLogout} className="btn-secondary">
            Logout
          </button>
        </div>
      </div>
    </header>
  );
}
