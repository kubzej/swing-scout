import { useEffect, useState } from 'react';

export function usePathname() {
  const [pathname, setPathname] = useState(() => window.location.pathname || '/');

  useEffect(() => {
    const handlePopState = () => {
      setPathname(window.location.pathname || '/');
    };

    window.addEventListener('popstate', handlePopState);
    return () => {
      window.removeEventListener('popstate', handlePopState);
    };
  }, []);

  const navigate = (nextPath: string, options?: { replace?: boolean }) => {
    if (nextPath === window.location.pathname) {
      setPathname(nextPath);
      return;
    }

    if (options?.replace) {
      window.history.replaceState({}, '', nextPath);
    } else {
      window.history.pushState({}, '', nextPath);
    }
    setPathname(nextPath);
  };

  return { pathname, navigate };
}
