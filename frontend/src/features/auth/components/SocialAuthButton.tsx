import type { ReactNode } from "react";

interface SocialAuthButtonProps {
  children: ReactNode;
  icon: ReactNode;
  loading: boolean;
  loadingText: string;
  onClick: () => void;
}

export function SocialAuthButton({
  children,
  icon,
  loading,
  loadingText,
  onClick,
}: SocialAuthButtonProps) {
  return (
    <button
      className="social-auth-button"
      type="button"
      onClick={onClick}
      disabled={loading}
    >
      <span className="social-auth-icon">{icon}</span>
      {loading ? loadingText : children}
    </button>
  );
}
