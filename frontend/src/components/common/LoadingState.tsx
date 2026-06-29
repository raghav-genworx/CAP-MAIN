interface LoadingStateProps {
  label: string;
}

export function LoadingState({ label }: LoadingStateProps) {
  return (
    <main className="centered-state" aria-busy="true">
      <p>{label}</p>
    </main>
  );
}
