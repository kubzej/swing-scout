import { useState, type FormEvent } from 'react';
import { AlertTriangle, LockKeyhole, LogIn } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useAuth } from '@/contexts/auth-context';

export function LoginPage() {
  const { signInWithPassword } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);

    const result = await signInWithPassword(email, password);
    setSubmitting(false);

    if (result.error) {
      setError(result.error);
    }
  };

  return (
    <div className="grid min-h-screen place-items-center px-4">
      <div className="w-full max-w-md rounded-[1.75rem] border border-border bg-card/90 p-8 shadow-2xl shadow-black/20 backdrop-blur">
        <div className="mb-8 space-y-3">
          <div className="inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-primary text-primary-foreground">
            <LockKeyhole className="h-5 w-5" />
          </div>
          <div className="space-y-2">
            <div className="text-xs uppercase tracking-[0.24em] text-primary/80">SwingScout</div>
            <h1 className="text-3xl font-semibold tracking-tight text-foreground">Přihlášení</h1>
            <p className="text-sm leading-6 text-muted-foreground">
              Přihlas se normálně přes e-mail a heslo ze Supabase účtu.
            </p>
          </div>
        </div>

        <form className="space-y-4" onSubmit={handleSubmit}>
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground" htmlFor="email">
              E-mail
            </label>
            <Input
              id="email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
              placeholder="jakub@example.com"
            />
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground" htmlFor="password">
              Heslo
            </label>
            <Input
              id="password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              placeholder="••••••••"
            />
          </div>

          <Button className="w-full" disabled={submitting} type="submit">
            <LogIn className="mr-2 h-4 w-4" />
            {submitting ? 'Přihlašuji…' : 'Přihlásit se'}
          </Button>
        </form>

        {error ? (
          <div className="mt-4 flex items-start gap-3 rounded-2xl border border-rose-400/30 bg-rose-400/10 p-4 text-sm text-rose-100">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <p>{error}</p>
          </div>
        ) : null}
      </div>
    </div>
  );
}
