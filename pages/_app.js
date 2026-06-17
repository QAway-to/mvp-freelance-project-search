import { useEffect } from 'react'
import '../src/styles/global.css'

export default function App({ Component, pageProps }) {
  useEffect(() => {
    fetch('/api/wake').catch(() => {})
  }, [])
  return <Component {...pageProps} />
}

