import * as React from 'react';

import GlobalStyles from '@mui/material/GlobalStyles';

import { AuthGuard } from '@/components/auth/auth-guard';
import ClientLayout from '@/components/dashboard/layout/client-layout';

interface LayoutProps {
  children: React.ReactNode;
}

export default function Layout({ children }: LayoutProps): React.JSX.Element {

  return (
    <AuthGuard>
      <GlobalStyles
        styles={{
          body: {
            '--MainNav-height': '65px',
            '--MainNav-zIndex': 1000,
            '--Footer-height': '100px',
            '--Footer-zIndex': 1000,
            '--Footer-height-mobile': '150px',
            '--Footer-zIndex-mobile': 1000,
            '--SideNav-width': '260px',
            '--SideNav-zIndex': 1100,
            '--MobileNav-width': '300px',
            '--MobileNav-zIndex': 1100,
          },
        }}
      />
      <ClientLayout> {children} </ClientLayout>
    </AuthGuard>
  );
}
