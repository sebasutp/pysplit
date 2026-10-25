import { AuthProvider } from './hooks/useAuth'
import { ToastProvider } from './hooks/useToast'
import { Footer } from './components/layout/Footer'
import { Header } from './components/layout/Header'
import { AppRoutes } from './router'
import './services/i18n'

export default function App() {
  return (
    <AuthProvider>
      <ToastProvider>
        <div className="flex min-h-screen flex-col bg-background text-foreground">
          <Header />
          <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8">
            <AppRoutes />
          </main>
          <Footer />
        </div>
      </ToastProvider>
    </AuthProvider>
  )
}
