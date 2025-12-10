import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

import { useAuth } from '@/auth/AuthContext';

const AuthCallback: React.FC = () => {
  const navigate = useNavigate();
  const { refreshUser } = useAuth();

  useEffect(() => {
    const completeLogin = async () => {
      try {
        // NOTE: FastAPI Users backend has already processed the GitHub callback,
        // which includes exchanging the code, creating the user, and setting
        // the cookie.
        await refreshUser();

        navigate('/', { replace: true });
      } catch (err) {
        console.error('OAuth post-login failed:', err);
        navigate('/login', { replace: true });
      }
    };

    completeLogin();
  }, [navigate, refreshUser]);

  return (
    <div className="flex items-center justify-center h-screen">
      <h1 className="text-xl font-semibold">Signing you in…</h1>
    </div>
  );
};

export default AuthCallback;
